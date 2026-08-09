# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from jiuwenswarm.server.live_voice.w2_demo_gate import (
    MAX_W2_EVIDENCE_IDS,
    MAX_W2_GATE_RECORDS,
    MAX_W2_PROVIDER_LABELS,
    W2AutomatedVerificationEvidence,
    W2CandidateEvidence,
    W2CapabilityPlane,
    W2EvidenceArtifact,
    W2EvidenceArtifactSlot,
    W2EvidenceKind,
    W2EvidenceTrustPolicy,
    W2FaultEvidence,
    W2GateContractViolation,
    W2GateStatus,
    W2Invariant,
    W2InvariantEvidence,
    W2JourneyStep,
    W2JourneyStepEvidence,
    W2LedgerAward,
    W2LedgerItem,
    W2RestartEvidence,
    W2ReconciliationOutcome,
    W2RouteClass,
    W2Section,
    W2ShowcaseRun,
    W2TaskReconciliationEvidence,
    _derive_v2_fault_class,
    _derive_v2_journey_steps,
    _derive_v2_restart,
    _derive_v2_restart_details,
    _derive_v2_runtime_items,
    _has_v2_claim_attestation,
    _common_v2_journey_runtime_ids,
    _observations_are_ordered,
    evaluate_w2_demo_gate,
    verify_w2_assisted_receipt_content,
    verify_w2_evidence_content,
    verify_w2_runtime_jsonl_content,
    w2_artifact_signature_payload,
)
from jiuwenswarm.server.live_voice.observability import (
    LIVE_VOICE_CONTRACT_VERSION,
    LiveVoiceObservation,
    OBSERVABILITY_SCHEMA_VERSION,
    create_observation,
)


_ITEM_MAX = {
    W2LedgerItem.P1_AUDIO: 5,
    W2LedgerItem.P1_RECOGNITION: 6,
    W2LedgerItem.P1_SYNTHESIS: 5,
    W2LedgerItem.P1_COMMIT_DEGRADATION: 4,
    W2LedgerItem.P2_RUNTIME: 10,
    W2LedgerItem.P2_MEDIA: 8,
    W2LedgerItem.P2_ENGINE: 8,
    W2LedgerItem.P2_AGENT: 8,
    W2LedgerItem.P2_PRESENTATION: 6,
    W2LedgerItem.P3_CORE: 8,
    W2LedgerItem.P3_EXECUTOR: 6,
    W2LedgerItem.P3_VOICE_BRIDGE: 5,
    W2LedgerItem.P3_PROGRESS: 4,
    W2LedgerItem.P3_UI: 2,
    W2LedgerItem.CROSS_ROUTE: 4,
    W2LedgerItem.CROSS_CONTEXT: 3,
    W2LedgerItem.CROSS_FAILURE: 3,
    W2LedgerItem.CROSS_OBSERVABILITY: 3,
    W2LedgerItem.CROSS_FLAG_OFF: 2,
}

_CANDIDATE_SHA = "a" * 40

_SIGNERS = {kind: f"test-{kind.value}-signer" for kind in W2EvidenceKind}
_PRINCIPALS = {kind: f"test-{kind.value}-principal" for kind in W2EvidenceKind}
_PRIVATE_KEYS = {kind: Ed25519PrivateKey.generate() for kind in W2EvidenceKind}
_GATEWAY_RUNTIME_SIGNER = "test-real-runtime-gateway-signer"
_GATEWAY_RUNTIME_PRINCIPAL = "test-real-runtime-gateway-principal"
_GATEWAY_RUNTIME_PRIVATE_KEY = Ed25519PrivateKey.generate()


def test_root_authorized_artifact_slot_requires_exact_nonempty_subjects() -> None:
    with pytest.raises(W2GateContractViolation, match="non-empty exact subjects"):
        W2EvidenceArtifactSlot(
            artifact_id="planned-runtime",
            artifact_sequence=1,
            evidence_kind=W2EvidenceKind.REAL_RUNTIME,
            signer_id="runtime-signer",
        )


def test_cross_producer_order_uses_event_time_not_artifact_slot_order() -> None:
    gateway_record = create_observation(
        json.loads(
            _runtime_content("order-gateway", "speech.recognition")
            .decode()
            .splitlines()[0]
        )["record"]
    )
    agentserver_record = create_observation(
        json.loads(
            _runtime_content("order-agent", "agent.dispatch").decode().splitlines()[0]
        )["record"]
    )
    gateway_first = replace(gateway_record, observed_at="2026-08-07T20:00:00Z")
    agentserver_first = replace(agentserver_record, observed_at="2026-08-07T20:00:01Z")
    gateway_second = replace(gateway_record, observed_at="2026-08-07T20:00:02Z")
    agentserver_second = replace(agentserver_record, observed_at="2026-08-07T20:00:03Z")
    positions = {
        id(gateway_first): ("gateway-artifact", 0),
        id(gateway_second): ("gateway-artifact", 1),
        id(agentserver_first): ("agentserver-artifact", 0),
        id(agentserver_second): ("agentserver-artifact", 1),
    }

    assert _observations_are_ordered(
        positions,
        gateway_first,
        agentserver_first,
        gateway_second,
        agentserver_second,
    )
    assert not _observations_are_ordered(
        positions,
        gateway_second,
        agentserver_first,
    )


def test_v2_gate_steps_must_share_one_exact_runtime_artifact_set() -> None:
    common = {"gateway-runtime", "agentserver-runtime"}
    assert _common_v2_journey_runtime_ids(
        [set(common) for _ in W2JourneyStep]
    ) == frozenset(common)
    mixed = [set(common) for _ in W2JourneyStep]
    mixed[-1] = {"unrelated-runtime"}
    assert not _common_v2_journey_runtime_ids(mixed)


_TRUST_POLICY = W2EvidenceTrustPolicy(
    public_keys={
        **{
            _SIGNERS[kind]: key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            for kind, key in _PRIVATE_KEYS.items()
        },
        _GATEWAY_RUNTIME_SIGNER: _GATEWAY_RUNTIME_PRIVATE_KEY.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ),
    },
    signer_roles={
        **{_SIGNERS[kind]: frozenset({kind}) for kind in W2EvidenceKind},
        _GATEWAY_RUNTIME_SIGNER: frozenset({W2EvidenceKind.REAL_RUNTIME}),
    },
    principal_ids={
        **{_SIGNERS[kind]: _PRINCIPALS[kind] for kind in W2EvidenceKind},
        _GATEWAY_RUNTIME_SIGNER: _GATEWAY_RUNTIME_PRINCIPAL,
    },
    producer_ids={
        **{
            _SIGNERS[kind]: (
                "agentserver" if kind is W2EvidenceKind.REAL_RUNTIME else None
            )
            for kind in W2EvidenceKind
        },
        _GATEWAY_RUNTIME_SIGNER: "gateway",
    },
)


def _trust_args(
    kind: W2EvidenceKind,
    content: bytes,
    *,
    artifact_id: str,
    sequence: int,
    source_label: str | None = None,
    artifact_kind: str | None = None,
) -> dict[str, object]:
    payload_kind = (
        artifact_kind
        or {
            W2EvidenceKind.REAL_RUNTIME: "runtime_jsonl",
            W2EvidenceKind.AUTOMATED_CONFORMANCE: "automated_report",
            W2EvidenceKind.INDEPENDENT_REVIEW: "assisted_receipt",
            W2EvidenceKind.FAULT_INJECTION: "assisted_receipt",
            W2EvidenceKind.HUMAN_OBSERVATION: "assisted_receipt",
        }[kind]
    )
    payload = w2_artifact_signature_payload(
        kind=payload_kind,
        artifact_id=artifact_id,
        sequence=sequence,
        source_label=source_label,
        content=content,
    )
    return {
        "trust_policy": _TRUST_POLICY,
        "signer_id": _SIGNERS[kind],
        "signature_hex": _PRIVATE_KEYS[kind].sign(payload).hex(),
    }


def _runtime_trust_args(
    content: bytes,
    *,
    artifact_id: str,
    sequence: int,
    producer_id: str,
) -> dict[str, object]:
    payload = w2_artifact_signature_payload(
        kind="runtime_jsonl",
        artifact_id=artifact_id,
        sequence=sequence,
        source_label=None,
        content=content,
    )
    if producer_id == "gateway":
        return {
            "trust_policy": _TRUST_POLICY,
            "signer_id": _GATEWAY_RUNTIME_SIGNER,
            "signature_hex": _GATEWAY_RUNTIME_PRIVATE_KEY.sign(payload).hex(),
        }
    return _trust_args(
        W2EvidenceKind.REAL_RUNTIME,
        content,
        artifact_id=artifact_id,
        sequence=sequence,
    )


def _candidate(**overrides: object) -> W2CandidateEvidence:
    values: dict[str, object] = {
        "candidate_sha": _CANDIDATE_SHA,
        "environment_id": "environment-1",
        "session_id": "session-1",
        "mode_id": "integrated-formal",
        "project_label": "project-w2",
        "model_labels": ("agent-model-1", "speech-model-1"),
        "provider_labels": ("speech-provider-1", "agent-provider-1"),
        "executor_label": "direct-d0-executor",
        "browser_label": "chrome-150",
        "os_label": "windows-11-build-26200",
        "device_label": "default-microphone-and-speakers",
        "network_label": "localhost-controlled",
        "origin_security_label": "localhost-secure-context",
        "worktree_clean": True,
        "isolated_runtime_data_observed": True,
        "secrets_boundary_recorded": True,
        "routes_and_flags_recorded": True,
        "real_source_facts_observed": True,
        "sanitized_route_trace_observed": True,
        "active_planes": frozenset(W2CapabilityPlane),
    }
    values.update(overrides)
    return W2CandidateEvidence(**values)  # type: ignore[arg-type]


_ITEM_RUNTIME_RECORDS = {
    W2LedgerItem.P1_AUDIO: (
        ("product.w2.media.capture", "speech.capture", "segment.completed"),
        ("product.w2.browser.playout", "speech.playout", "segment.completed"),
    ),
    W2LedgerItem.P1_RECOGNITION: (
        ("product.w2.speech.recognize", "speech.recognition", "segment.completed"),
    ),
    W2LedgerItem.P1_SYNTHESIS: (
        ("product.w2.speech.synthesize", "speech.synthesis", "segment.completed"),
    ),
    W2LedgerItem.P1_COMMIT_DEGRADATION: (
        ("product.w2.speech.recognize", "speech.recognition", "segment.completed"),
        ("product.w2.p2.submit.agent", "runtime.turn", "segment.completed"),
        (
            "product.w2.text.degradation",
            "system.degradation",
            "degradation.activated",
        ),
    ),
    W2LedgerItem.P2_RUNTIME: (
        ("product.w2.p2.activate", "runtime.queue", "segment.completed"),
        ("product.w2.p2.submit.agent", "runtime.turn", "segment.completed"),
        ("product.w2.p2.close", "runtime.queue", "segment.completed"),
    ),
    W2LedgerItem.P2_MEDIA: (
        ("product.w2.media.capture", "speech.capture", "segment.completed"),
        ("product.w2.browser.playout", "speech.playout", "segment.completed"),
        ("product.w2.media.downlink", "runtime.queue", "segment.completed"),
        ("product.w2.media.duplex", "runtime.queue", "segment.completed"),
    ),
    W2LedgerItem.P2_ENGINE: (
        ("product.w2.p2.notification", "agent.progress", "segment.completed"),
        ("product.w2.p2.barge", "speech.playout", "cancel.acknowledged"),
    ),
    W2LedgerItem.P2_AGENT: (
        ("product.w2.p2.submit.agent", "agent.dispatch", "segment.completed"),
        ("product.w2.p2.notification", "agent.progress", "segment.completed"),
    ),
    W2LedgerItem.P2_PRESENTATION: (
        ("product.w2.p2.presentation", "runtime.presentation", "segment.completed"),
    ),
    W2LedgerItem.P3_CORE: tuple(
        (f"product.w2.task.{operation}", segment, "segment.completed")
        for operation, segment in (
            ("create", "task.command"),
            ("get", "task.progress"),
            ("list", "runtime.queue"),
            ("status", "task.progress"),
            ("cancel", "task.command"),
            ("events", "task.progress"),
        )
    ),
    W2LedgerItem.P3_EXECUTOR: (
        ("product.w2.task.d0", "task.attempt", "segment.completed"),
    ),
    W2LedgerItem.P3_VOICE_BRIDGE: (
        ("product.voice_task_origin", "runtime.turn", "segment.completed"),
        ("product.voice_task_bridge", "task.command", "segment.completed"),
    ),
    W2LedgerItem.P3_PROGRESS: (
        ("product.w2.task.status", "task.progress", "segment.completed"),
        ("product.w2.task.events", "task.progress", "segment.completed"),
        ("product.w2.p3.progress", "task.progress", "segment.completed"),
    ),
    W2LedgerItem.P3_UI: (("product.w2.p3.ui", "task.progress", "segment.completed"),),
    W2LedgerItem.CROSS_ROUTE: (
        ("product.w2.speech.recognize", "speech.recognition", "segment.completed"),
        ("product.w2.p2.submit.agent", "agent.dispatch", "segment.completed"),
        ("product.w2.task.create", "task.command", "segment.completed"),
    ),
    W2LedgerItem.CROSS_CONTEXT: (
        ("product.w2.p2.submit.agent", "runtime.turn", "segment.completed"),
        ("product.w2.p2.submit.agent", "agent.dispatch", "segment.completed"),
        ("product.w2.task.create", "task.command", "segment.completed"),
    ),
    W2LedgerItem.CROSS_FAILURE: (
        ("product.w2.fault", "runtime.turn", "failure.observed"),
        (
            "product.w2.text.degradation",
            "system.degradation",
            "degradation.activated",
        ),
    ),
    W2LedgerItem.CROSS_OBSERVABILITY: (
        ("product.w2.observability", "runtime.queue", "segment.completed"),
        ("product.w2.fault", "runtime.turn", "failure.observed"),
    ),
}

_JOURNEY_RUNTIME_RECORDS = (
    ("product.w2.speech.recognize", "speech.recognition", "segment.completed"),
    ("product.w2.p2.submit.agent", "agent.dispatch", "segment.completed"),
    ("product.w2.speech.synthesize", "speech.synthesis", "segment.completed"),
    ("product.w2.journey.agent_speech", "runtime.turn", "segment.completed"),
    ("product.w2.p2.barge", "speech.playout", "cancel.acknowledged"),
    ("product.w2.journey.interruption", "runtime.turn", "segment.completed"),
    ("product.voice_task_origin", "runtime.turn", "segment.completed"),
    ("product.voice_task_bridge", "task.command", "segment.completed"),
    ("product.w2.journey.task_create", "runtime.turn", "segment.completed"),
    ("product.w2.task.create", "task.command", "segment.completed"),
    (
        "product.w2.journey.conversation_during_task",
        "runtime.turn",
        "segment.completed",
    ),
    ("product.w2.task.status", "task.progress", "segment.completed"),
    ("product.w2.task.events", "task.progress", "segment.completed"),
    ("product.w2.p3.progress", "task.progress", "segment.completed"),
    ("product.w2.journey.task_result", "runtime.turn", "segment.completed"),
    ("product.w2.p2.submit.agent", "runtime.turn", "segment.completed"),
    (
        "product.w2.text.degradation",
        "system.degradation",
        "degradation.activated",
    ),
    ("product.w2.journey.text_degradation", "runtime.turn", "segment.completed"),
    ("product.w2.task.create", "task.command", "segment.completed"),
    ("product.w2.observability", "runtime.queue", "segment.completed"),
    ("product.w2.journey.route_telemetry", "runtime.turn", "segment.completed"),
)


def _binding(segment: str, token: str, *, task_id: str | None = None):
    value: dict[str, object] = {"correlation_id": f"correlation-{token}"}
    if segment in {"speech.capture", "speech.recognition"}:
        value["interaction_id"] = f"interaction-{token}"
    elif segment in {
        "speech.synthesis",
        "speech.playout",
        "runtime.response",
        "runtime.presentation",
    }:
        value["interaction_id"] = f"interaction-{token}"
        value["response_id"] = f"response-{token}"
        value["response_generation"] = 1
    elif segment == "runtime.turn":
        value["interaction_id"] = f"interaction-{token}"
        value["turn_id"] = f"turn-{token}"
    elif segment.startswith("agent."):
        value["round_id"] = f"round-{token}"
    elif segment.startswith("task."):
        value["task_id"] = task_id or f"task-{token}"
        if segment == "task.attempt":
            value["attempt_id"] = f"attempt-{token}"
    return value


def _route(subject: str):
    return {
        "implementation_class": "formal",
        "owner_module": "product.composition",
        "capability_provider": (
            "formal-dedicated-media"
            if subject == f"evidence-{W2LedgerItem.P2_MEDIA.value}"
            else "w2-test-runtime"
        ),
        "contract_version": LIVE_VOICE_CONTRACT_VERSION,
        "reason_code": None,
    }


def _runtime_content(
    subject: str,
    segment: str | tuple[str, ...],
    *,
    fault: bool = False,
    task_id: str | None = None,
    environment_id: str = "environment-1",
) -> bytes:
    token = hashlib.sha256(subject.encode()).hexdigest()[:16]
    segments = (segment,) if isinstance(segment, str) else segment
    fact_records: tuple[tuple[str, str, str], ...]
    if subject.startswith("evidence-"):
        item_label = subject.removeprefix("evidence-").removesuffix("-attestation")
        item = W2LedgerItem(item_label)
        fact_records = _ITEM_RUNTIME_RECORDS[item]
    elif subject == "journey-runtime":
        fact_records = _JOURNEY_RUNTIME_RECORDS
        task_id = "task-journey-1"
    elif subject.startswith("showcase-") and subject.endswith("-runtime"):
        number = subject.removeprefix("showcase-").removesuffix("-runtime")
        fact_records = (
            (f"product.w2.showcase.{number}", "runtime.turn", "segment.completed"),
        )
    elif subject.startswith("fault-") and subject.endswith("-runtime"):
        core = subject.removeprefix("fault-").removesuffix("-runtime")
        if core.endswith("-non-retriable"):
            plane, fault_class = core.removesuffix("-non-retriable"), "non_retriable"
        elif core.endswith("-zero-effect"):
            plane, fault_class = core.removesuffix("-zero-effect"), "zero_effect"
        else:
            plane, fault_class = core.removesuffix("-retriable"), "retriable"
        fact_records = (
            (
                f"product.w2.fault_marker.{plane.replace('.', '_')}.{fault_class}",
                "runtime.turn",
                "failure.observed",
            ),
        )
    else:
        fact_records = tuple(
            (
                "w2.test_runtime",
                segment_name,
                (
                    "degradation.activated"
                    if segment_name == "system.degradation"
                    else ("segment.failed" if fault else "segment.completed")
                ),
            )
            for segment_name in segments
        )
    records = []
    for index, (source_component, segment_name, event_name) in enumerate(fact_records):
        segment_token = f"{token}-{index}"
        binding = _binding(segment_name, token, task_id=task_id)
        common = {
            "schema_version": OBSERVABILITY_SCHEMA_VERSION,
            "segment_name": segment_name,
            "observed_at": "2026-08-07T20:00:00Z",
            "monotonic_ms": float(index + 1),
            "binding": binding,
            "route": _route(subject),
            "source_component": source_component,
        }
        if event_name == "degradation.activated":
            records.append(
                create_observation(
                    {
                        **common,
                        "event_id": f"degradation-{segment_token}",
                        "event_name": "degradation.activated",
                        "reason_code": "DEGRADED",
                    }
                )
            )
        elif event_name in {"segment.failed", "failure.observed"}:
            if segment_name.startswith("speech."):
                reason_code, error_code = "PROVIDER_FAILURE", "INTERNAL"
            elif segment_name.startswith("agent."):
                reason_code, error_code = "AGENT_FAILURE", "INTERNAL"
            elif segment_name.startswith("task."):
                reason_code, error_code = "TASK_FAILURE", "INTERNAL"
            else:
                reason_code, error_code = "UNAVAILABLE", "UNAVAILABLE"
            records.append(
                create_observation(
                    {
                        **common,
                        "event_id": f"failed-{segment_token}",
                        "event_name": event_name,
                        **(
                            {
                                "source_record_id": f"record-{segment_token}",
                                "state": "failed",
                                "outcome": "failed",
                                "duration_ms": 1.0,
                            }
                            if event_name == "segment.failed"
                            else {}
                        ),
                        "reason_code": reason_code,
                        "error_code": error_code,
                    }
                )
            )
        elif event_name == "cancel.acknowledged":
            records.append(
                create_observation(
                    {
                        **common,
                        "event_id": f"cancel-{segment_token}",
                        "event_name": event_name,
                        "reason_code": "CANCEL_ACKNOWLEDGED",
                        "cancel_scope": "playback.stop",
                    }
                )
            )
        else:
            records.extend(
                (
                    create_observation(
                        {
                            **common,
                            "event_id": f"route-{segment_token}",
                            "event_name": "route.selected",
                        }
                    ),
                    create_observation(
                        {
                            **common,
                            "event_id": f"completed-{segment_token}",
                            "event_name": "segment.completed",
                            "source_record_id": f"record-{segment_token}",
                            "state": "terminal",
                            "outcome": "completed",
                            "duration_ms": 1.0,
                        }
                    ),
                )
            )
    lines = []
    for sequence, record in enumerate(records):
        lines.append(
            json.dumps(
                {
                    "evidence_schema": "live-voice.w2-jsonl-evidence.v1",
                    "candidate": {
                        "candidate_sha": _CANDIDATE_SHA,
                        "environment_id": environment_id,
                        "session_id": "session-1",
                        "mode_id": "integrated-formal",
                    },
                    "record_kind": "observation",
                    "sequence": sequence,
                    "record": record.to_dict(),
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
    return ("\n".join(lines) + "\n").encode()


def _v2_runtime_content(
    legacy_content: bytes,
    *,
    artifact_id: str,
    artifact_sequence: int,
    producer_id: str = "agentserver",
    process_epoch: str = "agentserver-epoch-1",
    predecessor_artifact_id: str | None = None,
) -> bytes:
    records = [json.loads(line) for line in legacy_content.decode().splitlines()]
    for envelope in records:
        envelope["evidence_schema"] = "live-voice.w2-jsonl-evidence.v2"
        record = envelope["record"]
        source = record["source_component"]
        if not source.startswith(("product.w2.", "product.voice_task_")):
            segment = record["segment_name"]
            if producer_id == "gateway":
                record["source_component"] = {
                    "speech.capture": "product.w2.media.capture",
                    "speech.recognition": "product.w2.speech.recognize",
                    "speech.synthesis": "product.w2.speech.synthesize",
                }.get(segment, source)
            else:
                record["source_component"] = {
                    "runtime.turn": "product.w2.p2.submit.agent",
                    "agent.dispatch": "product.w2.p2.submit.agent",
                    "agent.progress": "product.w2.agent.final",
                    "runtime.presentation": "product.w2.p2.presentation",
                    "runtime.queue": "product.w2.p2.activate",
                    "task.command": "product.w2.task.create",
                    "task.progress": "product.w2.task.status",
                    "task.attempt": "product.w2.task.d0",
                }.get(segment, source)
    for index, envelope in enumerate(records):
        record = envelope["record"]
        if record["event_name"] != "route.selected":
            continue
        matching = next(
            later["record"]
            for later in records[index + 1 :]
            if later["record"]["event_name"] == "segment.completed"
            and later["record"]["source_component"] == record["source_component"]
            and later["record"]["segment_name"] == record["segment_name"]
            and later["record"]["binding"] == record["binding"]
        )
        record["source_record_id"] = matching["source_record_id"]
    candidate = records[0]["candidate"]
    header = {
        "evidence_schema": "live-voice.w2-jsonl-evidence.v2",
        "record_kind": "header",
        "evidence_set_id": "evidence-set-1",
        "artifact_id": artifact_id,
        "artifact_sequence": artifact_sequence,
        "producer_id": producer_id,
        "process_epoch": process_epoch,
        "predecessor_artifact_id": predecessor_artifact_id,
        "repository_path": str(Path(__file__).resolve().parents[3]),
        "candidate": candidate,
    }
    footer = {
        "evidence_schema": "live-voice.w2-jsonl-evidence.v2",
        "record_kind": "footer",
        "artifact_id": artifact_id,
        "record_count": len(records),
        "last_sequence": len(records) - 1,
        "accepted_observations": len(records),
        "accepted_metrics": 0,
        "rejected_invalid": 0,
        "rejected_capacity": 0,
        "failed_writes": 0,
        "closed": True,
    }
    return (
        "\n".join(
            json.dumps(item, separators=(",", ":"), sort_keys=True)
            for item in (header, *records, footer)
        )
        + "\n"
    ).encode()


def _v2_failure_artifact(
    *,
    artifact_id: str,
    artifact_sequence: int,
    segment_name: str,
    reason_code: str,
    error_code: str,
) -> W2EvidenceArtifact:
    producer_id = "gateway" if segment_name.startswith("speech.") else "agentserver"
    legacy = _runtime_content(artifact_id, segment_name, fault=True)
    envelopes = [json.loads(line) for line in legacy.decode().splitlines()]
    failed = envelopes[0]["record"]
    failed["reason_code"] = reason_code
    failed["error_code"] = error_code
    legacy = ("\n".join(json.dumps(item) for item in envelopes) + "\n").encode()
    content = _v2_runtime_content(
        legacy,
        artifact_id=artifact_id,
        artifact_sequence=artifact_sequence,
        producer_id=producer_id,
    )
    return verify_w2_runtime_jsonl_content(
        artifact_id=artifact_id,
        sequence=artifact_sequence,
        content=content,
        **_runtime_trust_args(
            content,
            artifact_id=artifact_id,
            sequence=artifact_sequence,
            producer_id=producer_id,
        ),
    )


def _v2_task_state_artifact(
    *,
    artifact_id: str,
    artifact_sequence: int,
    process_epoch: str,
    source_seq: int,
    state: str,
    outcome: str | None,
    predecessor_artifact_id: str | None = None,
) -> W2EvidenceArtifact:
    facts: dict[str, object] = {
        "schema_version": OBSERVABILITY_SCHEMA_VERSION,
        "event_id": f"event-{artifact_id}",
        "event_name": "task.state_observed",
        "segment_name": "task.progress",
        "observed_at": "2026-08-07T20:00:00Z",
        "monotonic_ms": float(source_seq),
        "binding": {
            "correlation_id": "correlation-restart",
            "task_id": "task-restart-v2",
            "attempt_id": "attempt-restart-v2",
        },
        "route": _route(artifact_id),
        "source_component": (
            "product.w2.task.reconciliation"
            if state == "terminal"
            else "product.w2.task.event"
        ),
        "source_event_id": f"task-event-{source_seq}",
        "source_occurred_at": "2026-08-07T20:00:00Z",
        "source_seq": source_seq,
        "state": state,
        "outcome": outcome,
    }
    observation = create_observation(facts)
    legacy = (
        json.dumps(
            {
                "evidence_schema": "live-voice.w2-jsonl-evidence.v1",
                "candidate": {
                    "candidate_sha": _CANDIDATE_SHA,
                    "environment_id": "environment-1",
                    "session_id": "session-1",
                    "mode_id": "integrated-formal",
                },
                "record_kind": "observation",
                "sequence": 0,
                "record": observation.to_dict(),
            }
        )
        + "\n"
    ).encode()
    content = _v2_runtime_content(
        legacy,
        artifact_id=artifact_id,
        artifact_sequence=artifact_sequence,
        process_epoch=process_epoch,
        predecessor_artifact_id=predecessor_artifact_id,
    )
    return verify_w2_runtime_jsonl_content(
        artifact_id=artifact_id,
        sequence=artifact_sequence,
        content=content,
        **_trust_args(
            W2EvidenceKind.REAL_RUNTIME,
            content,
            artifact_id=artifact_id,
            sequence=artifact_sequence,
        ),
    )


def _task_completed_records(
    *,
    source_component: str,
    segment_name: str,
    task_id: str,
    attempt_id: str,
    token: str,
) -> tuple[LiveVoiceObservation, LiveVoiceObservation]:
    source_record_id = f"record-{token}"
    common = {
        "schema_version": OBSERVABILITY_SCHEMA_VERSION,
        "segment_name": segment_name,
        "observed_at": "2026-08-07T20:00:00Z",
        "monotonic_ms": 1.0,
        "binding": {
            "correlation_id": f"correlation-{task_id}",
            "task_id": task_id,
            "attempt_id": attempt_id,
        },
        "route": _route(token),
        "source_component": source_component,
        "source_record_id": source_record_id,
    }
    return (
        create_observation(
            {
                **common,
                "event_id": f"route-{token}",
                "event_name": "route.selected",
            }
        ),
        create_observation(
            {
                **common,
                "event_id": f"completed-{token}",
                "event_name": "segment.completed",
                "state": "terminal",
                "outcome": "completed",
                "duration_ms": 1.0,
            }
        ),
    )


def _task_state_observation(
    *,
    task_id: str,
    attempt_id: str,
    source_seq: int,
    state: str,
    outcome: str | None,
    source_component: str,
    token: str,
) -> LiveVoiceObservation:
    facts: dict[str, object] = {
        "schema_version": OBSERVABILITY_SCHEMA_VERSION,
        "event_id": f"state-{token}",
        "event_name": "task.state_observed",
        "segment_name": "task.progress",
        "observed_at": (
            "2026-08-07T20:00:01Z"
            if source_component == "product.w2.task.reconciliation"
            else "2026-08-07T20:00:00Z"
        ),
        "monotonic_ms": float(source_seq),
        "binding": {
            "correlation_id": f"correlation-{task_id}",
            "task_id": task_id,
            "attempt_id": attempt_id,
        },
        "route": _route(token),
        "source_component": source_component,
        "source_event_id": f"source-{token}",
        "source_occurred_at": "2026-08-07T20:00:00Z",
        "source_seq": source_seq,
        "state": state,
        "outcome": outcome,
    }
    if outcome == "cancelled":
        facts["reason_code"] = "CANCEL_TERMINAL"
    elif outcome == "failed":
        facts["reason_code"] = "TASK_FAILURE"
    return create_observation(facts)


def _v2_agentserver_artifact(
    observations: tuple[LiveVoiceObservation, ...],
    *,
    artifact_id: str,
    artifact_sequence: int,
    process_epoch: str,
    predecessor_artifact_id: str | None = None,
) -> W2EvidenceArtifact:
    legacy = (
        "\n".join(
            json.dumps(
                {
                    "evidence_schema": "live-voice.w2-jsonl-evidence.v1",
                    "candidate": {
                        "candidate_sha": _CANDIDATE_SHA,
                        "environment_id": "environment-1",
                        "session_id": "session-1",
                        "mode_id": "integrated-formal",
                    },
                    "record_kind": "observation",
                    "sequence": sequence,
                    "record": observation.to_dict(),
                },
                separators=(",", ":"),
                sort_keys=True,
            )
            for sequence, observation in enumerate(observations)
        )
        + "\n"
    ).encode()
    content = _v2_runtime_content(
        legacy,
        artifact_id=artifact_id,
        artifact_sequence=artifact_sequence,
        producer_id="agentserver",
        process_epoch=process_epoch,
        predecessor_artifact_id=predecessor_artifact_id,
    )
    return verify_w2_runtime_jsonl_content(
        artifact_id=artifact_id,
        sequence=artifact_sequence,
        content=content,
        **_runtime_trust_args(
            content,
            artifact_id=artifact_id,
            sequence=artifact_sequence,
            producer_id="agentserver",
        ),
    )


def _v2_abc_retry_artifacts(
    *,
    cancel_attempt: str = "attempt-a",
    include_cancel_command: bool = True,
    cancel_outcome: str | None = "cancelled",
    cancel_terminal_before_command: bool = False,
    retry_attempts: tuple[str, ...] = ("attempt-b", "attempt-c"),
    d0_attempt: str = "attempt-b",
    execution_order: str = "normal",
    extra_retry_attempt: str | None = None,
) -> tuple[W2EvidenceArtifact, W2EvidenceArtifact]:
    task_id = "task-abc"
    records: list[LiveVoiceObservation] = []
    for operation, segment in (
        ("create", "task.command"),
        ("get", "task.progress"),
        ("list", "runtime.queue"),
        ("status", "task.progress"),
    ):
        records.extend(
            _task_completed_records(
                source_component=f"product.w2.task.{operation}",
                segment_name=segment,
                task_id=task_id,
                attempt_id="attempt-a",
                token=f"{operation}-a",
            )
        )
    cancelled = (
        _task_state_observation(
            task_id=task_id,
            attempt_id="attempt-a",
            source_seq=1,
            state="terminal",
            outcome=cancel_outcome,
            source_component="product.w2.task.event",
            token="cancelled-a",
        )
        if cancel_outcome is not None
        else None
    )
    if cancel_terminal_before_command and cancelled is not None:
        records.append(cancelled)
    if include_cancel_command:
        records.extend(
            _task_completed_records(
                source_component="product.w2.task.cancel",
                segment_name="task.command",
                task_id=task_id,
                attempt_id=cancel_attempt,
                token="cancel-a",
            )
        )
    if not cancel_terminal_before_command and cancelled is not None:
        records.append(cancelled)
    records.extend(
        _task_completed_records(
            source_component="product.w2.task.events",
            segment_name="task.progress",
            task_id=task_id,
            attempt_id="attempt-a",
            token="events-a",
        )
    )

    retry_records = [
        _task_completed_records(
            source_component="product.w2.task.retry",
            segment_name="task.command",
            task_id=task_id,
            attempt_id=attempt_id,
            token=f"retry-{index}-{attempt_id}",
        )
        for index, attempt_id in enumerate(retry_attempts)
    ]
    d0_records = _task_completed_records(
        source_component="product.w2.task.d0",
        segment_name="task.attempt",
        task_id=task_id,
        attempt_id=d0_attempt,
        token=f"d0-{d0_attempt}",
    )
    if execution_order == "d0_before_retry":
        records.extend(d0_records)
        for retry in retry_records:
            records.extend(retry)
    elif execution_order == "second_retry_before_d0":
        for retry in retry_records:
            records.extend(retry)
        records.extend(d0_records)
    else:
        if retry_records:
            records.extend(retry_records[0])
        records.extend(d0_records)
        for retry in retry_records[1:]:
            records.extend(retry)
    if extra_retry_attempt is not None:
        records.extend(
            _task_completed_records(
                source_component="product.w2.task.retry",
                segment_name="task.command",
                task_id=task_id,
                attempt_id=extra_retry_attempt,
                token=f"retry-{extra_retry_attempt}",
            )
        )
    records.append(
        _task_state_observation(
            task_id=task_id,
            attempt_id="attempt-b",
            source_seq=2,
            state="terminal",
            outcome="completed",
            source_component="product.w2.task.event",
            token="completed-b",
        )
    )
    records.append(
        _task_state_observation(
            task_id=task_id,
            attempt_id="attempt-c",
            source_seq=3,
            state="running",
            outcome=None,
            source_component="product.w2.task.event",
            token="running-c",
        )
    )
    predecessor = _v2_agentserver_artifact(
        tuple(records),
        artifact_id="agentserver-abc-before",
        artifact_sequence=1,
        process_epoch="agentserver-abc-epoch-before",
    )
    successor = _v2_agentserver_artifact(
        (
            _task_state_observation(
                task_id=task_id,
                attempt_id="attempt-c",
                source_seq=4,
                state="terminal",
                outcome="interrupted",
                source_component="product.w2.task.reconciliation",
                token="reconciled-c",
            ),
        ),
        artifact_id="agentserver-abc-after",
        artifact_sequence=2,
        process_epoch="agentserver-abc-epoch-after",
        predecessor_artifact_id=predecessor.artifact_id,
    )
    return predecessor, successor


def _v2_restart_pair(
    predecessor_facts: tuple[tuple[str, str, int, str, str | None], ...],
    successor_facts: tuple[tuple[str, str, int, str, str | None], ...],
    *,
    artifact_sequence_start: int = 1,
    artifact_prefix: str = "agentserver-restart",
) -> tuple[W2EvidenceArtifact, W2EvidenceArtifact]:
    predecessor = _v2_agentserver_artifact(
        tuple(
            _task_state_observation(
                task_id=task_id,
                attempt_id=attempt_id,
                source_seq=source_seq,
                state=state,
                outcome=outcome,
                source_component="product.w2.task.event",
                token=f"before-{index}-{task_id}-{attempt_id}",
            )
            for index, (task_id, attempt_id, source_seq, state, outcome) in enumerate(
                predecessor_facts
            )
        ),
        artifact_id=f"{artifact_prefix}-before",
        artifact_sequence=artifact_sequence_start,
        process_epoch="agentserver-restart-epoch-before",
    )
    successor = _v2_agentserver_artifact(
        tuple(
            _task_state_observation(
                task_id=task_id,
                attempt_id=attempt_id,
                source_seq=source_seq,
                state=state,
                outcome=outcome,
                source_component="product.w2.task.reconciliation",
                token=f"after-{index}-{task_id}-{attempt_id}",
            )
            for index, (task_id, attempt_id, source_seq, state, outcome) in enumerate(
                successor_facts
            )
        ),
        artifact_id=f"{artifact_prefix}-after",
        artifact_sequence=artifact_sequence_start + 1,
        process_epoch="agentserver-restart-epoch-after",
        predecessor_artifact_id=predecessor.artifact_id,
    )
    return predecessor, successor


def _assisted_content(
    artifact_id: str,
    sequence: int,
    receipt_type: str,
    observed_content_sha256: str,
    observed_subject: str,
) -> bytes:
    witness_kind = {
        "human_observation": W2EvidenceKind.HUMAN_OBSERVATION,
        "independent_review": W2EvidenceKind.INDEPENDENT_REVIEW,
        "fault_injection": W2EvidenceKind.FAULT_INJECTION,
        "runtime_attestation": W2EvidenceKind.REAL_RUNTIME,
    }[receipt_type]
    return json.dumps(
        {
            "schema": "live-voice.w2-assisted-receipt.v1",
            "receipt_type": receipt_type,
            "artifact_id": artifact_id,
            "sequence": sequence,
            "candidate": {
                "candidate_sha": _CANDIDATE_SHA,
                "environment_id": "environment-1",
                "session_id": "session-1",
                "mode_id": "integrated-formal",
            },
            "witness_id": _PRINCIPALS[witness_kind],
            "observed_subject": observed_subject,
            "observed_content_sha256": observed_content_sha256,
            "passed": True,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _assisted_v2_content(
    *,
    artifact_id: str,
    sequence: int,
    receipt_type: str,
    observed_content_sha256s: list[str],
    observed_subject: str,
    evidence_set_id: str = "evidence-set-1",
    previous_receipt_sha256: str | None = None,
) -> bytes:
    witness_kind = {
        "human_observation": W2EvidenceKind.HUMAN_OBSERVATION,
        "independent_review": W2EvidenceKind.INDEPENDENT_REVIEW,
        "fault_injection": W2EvidenceKind.FAULT_INJECTION,
        "runtime_attestation": W2EvidenceKind.REAL_RUNTIME,
    }[receipt_type]
    return json.dumps(
        {
            "schema": "live-voice.w2-assisted-receipt.v2",
            "receipt_type": receipt_type,
            "artifact_id": artifact_id,
            "sequence": sequence,
            "candidate": {
                "candidate_sha": _CANDIDATE_SHA,
                "environment_id": "environment-1",
                "session_id": "session-1",
                "mode_id": "integrated-formal",
            },
            "evidence_set_id": evidence_set_id,
            "witness_id": _PRINCIPALS[witness_kind],
            "observed_subject": observed_subject,
            "observed_content_sha256s": observed_content_sha256s,
            "previous_receipt_sha256": previous_receipt_sha256,
            "passed": True,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _awards() -> tuple[W2LedgerAward, ...]:
    results = []
    for item, maximum in _ITEM_MAX.items():
        evidence_id = f"evidence-{item.value}"
        points = maximum
        target_owned = points > 0
        if item is W2LedgerItem.CROSS_FLAG_OFF:
            kinds = frozenset({W2EvidenceKind.AUTOMATED_CONFORMANCE})
            evidence_ids = (evidence_id,)
        elif item in {W2LedgerItem.P1_AUDIO, W2LedgerItem.P3_UI}:
            kinds = frozenset(
                {W2EvidenceKind.REAL_RUNTIME, W2EvidenceKind.HUMAN_OBSERVATION}
            )
            evidence_ids = (evidence_id, f"{evidence_id}-attestation")
        elif item in {
            W2LedgerItem.CROSS_ROUTE,
            W2LedgerItem.CROSS_CONTEXT,
            W2LedgerItem.CROSS_OBSERVABILITY,
        }:
            kinds = frozenset({W2EvidenceKind.REAL_RUNTIME})
            evidence_ids = (evidence_id, f"{evidence_id}-attestation")
        elif item is W2LedgerItem.CROSS_FAILURE:
            kinds = frozenset(
                {W2EvidenceKind.REAL_RUNTIME, W2EvidenceKind.FAULT_INJECTION}
            )
            evidence_ids = (evidence_id, f"{evidence_id}-attestation")
        else:
            kinds = frozenset({W2EvidenceKind.REAL_RUNTIME})
            evidence_ids = (evidence_id,)
        results.append(
            W2LedgerAward(
                item=item,
                points=points,
                route_class=W2RouteClass.FORMAL,
                evidence_kinds=kinds,
                evidence_ids=evidence_ids,
                target_route_owned=target_owned,
            )
        )
    return tuple(results)


def _invariants() -> tuple[W2InvariantEvidence, ...]:
    return tuple(
        W2InvariantEvidence(invariant, True, (f"invariant-{invariant.value}",))
        for invariant in W2Invariant
    )


def _verification(**overrides: object) -> W2AutomatedVerificationEvidence:
    values: dict[str, object] = {
        "affected_python_passed": True,
        "affected_web_passed": True,
        "frontend_build_passed": True,
        "negative_fault_and_flag_off_passed": True,
        "required_reviews_passed": True,
        "unexplained_required_gaps_zero": True,
        "flaky_passes_zero": True,
        "evidence_ids": ("gate1-automated", "gate1-review"),
    }
    values.update(overrides)
    return W2AutomatedVerificationEvidence(**values)  # type: ignore[arg-type]


def _runs() -> tuple[W2ShowcaseRun, ...]:
    return tuple(
        W2ShowcaseRun(
            run_number,
            _CANDIDATE_SHA,
            "environment-1",
            "session-1",
            "integrated-formal",
            True,
            (f"showcase-{run_number}-runtime", f"showcase-{run_number}-human"),
        )
        for run_number in (1, 2, 3)
    )


def _journey() -> tuple[W2JourneyStepEvidence, ...]:
    return tuple(
        W2JourneyStepEvidence(
            step,
            True,
            (
                "journey-runtime",
                f"journey-{step.value}-human",
                *(
                    (f"journey-{step.value}-fault",)
                    if step is W2JourneyStep.TEXT_DEGRADATION
                    else ()
                ),
            ),
        )
        for step in W2JourneyStep
    )


def _faults() -> tuple[W2FaultEvidence, ...]:
    return tuple(
        W2FaultEvidence(
            plane,
            True,
            True,
            True,
            True,
            True,
            (
                f"fault-{plane.value}-retriable-runtime",
                f"fault-{plane.value}-retriable-attestation",
            ),
            (
                f"fault-{plane.value}-non-retriable-runtime",
                f"fault-{plane.value}-non-retriable-attestation",
            ),
            (
                f"fault-{plane.value}-zero-effect-runtime",
                f"fault-{plane.value}-zero-effect-attestation",
            ),
        )
        for plane in W2CapabilityPlane
    )


def _restart() -> W2RestartEvidence:
    return W2RestartEvidence(
        True,
        ("task-restart-1",),
        (
            W2TaskReconciliationEvidence(
                "task-restart-1",
                W2ReconciliationOutcome.TERMINAL,
                ("restart-1",),
            ),
        ),
        ("restart-1",),
    )


def _artifacts(values: dict[str, object]) -> tuple[W2EvidenceArtifact, ...]:
    claims: list[tuple[str, ...]] = []
    claims.extend(award.evidence_ids for award in values["awards"])  # type: ignore[union-attr]
    claims.extend(
        invariant.evidence_ids
        for invariant in values["invariants"]  # type: ignore[union-attr]
    )
    claims.append(values["verification"].evidence_ids)  # type: ignore[union-attr]
    claims.extend(run.evidence_ids for run in values["showcase_runs"])  # type: ignore[union-attr]
    claims.extend(step.evidence_ids for step in values["journey_steps"])  # type: ignore[union-attr]
    claims.extend(fault.evidence_ids for fault in values["faults"])  # type: ignore[union-attr]
    restart = values["restart"]  # type: ignore[assignment]
    claims.append(restart.evidence_ids)  # type: ignore[union-attr]
    claims.extend(
        item.evidence_ids
        for item in restart.reconciliations  # type: ignore[union-attr]
    )
    ordered_ids: list[str] = []
    for evidence_ids in claims:
        for evidence_id in evidence_ids:
            if evidence_id not in ordered_ids:
                ordered_ids.append(evidence_id)
    return tuple(
        _artifact_for_id(evidence_id, sequence)
        for sequence, evidence_id in enumerate(ordered_ids, start=1)
    )


def _runtime_spec(
    evidence_id: str,
) -> tuple[str | tuple[str, ...], bool, str | None] | None:
    prefix = "evidence-"
    if evidence_id.startswith(prefix):
        item_label = evidence_id.removeprefix(prefix).removesuffix("-attestation")
        item = W2LedgerItem(item_label)
        if item is W2LedgerItem.CROSS_FLAG_OFF:
            return None
        if item in {
            W2LedgerItem.CROSS_ROUTE,
            W2LedgerItem.CROSS_CONTEXT,
            W2LedgerItem.CROSS_OBSERVABILITY,
        }:
            return (
                (
                    "speech.recognition",
                    "runtime.turn",
                    "agent.dispatch",
                    "task.command",
                    "task.progress",
                ),
                False,
                "task-cross-1",
            )
        return "runtime.turn", False, "task-ledger-1"
    if evidence_id.startswith("showcase-") and evidence_id.endswith("-runtime"):
        return "runtime.turn", False, None
    if evidence_id == "journey-runtime":
        return "runtime.turn", False, "task-journey-1"
    if evidence_id.startswith("fault-") and evidence_id.endswith("-runtime"):
        segment = (
            "speech.capture"
            if "p1.speech_media" in evidence_id
            else (
                "agent.dispatch"
                if "p2.conversation" in evidence_id
                else ("task.command" if "p3.task" in evidence_id else "runtime.turn")
            )
        )
        return segment, True, None
    return None


def _automated_report(evidence_id: str) -> bytes:
    subjects = [f"automated:{evidence_id}"]
    if evidence_id.startswith("invariant-"):
        subjects.append(f"invariant:{evidence_id.removeprefix('invariant-')}")
    if evidence_id == "gate1-automated":
        subjects.append("review:gate1")
        subjects.extend(
            f"verification:{field_name}"
            for field_name in (
                "affected_python_passed",
                "affected_web_passed",
                "frontend_build_passed",
                "negative_fault_and_flag_off_passed",
                "required_reviews_passed",
                "unexplained_required_gaps_zero",
                "flaky_passes_zero",
            )
        )
        subjects.extend(
            f"candidate:{field_name}"
            for field_name in (
                "worktree_clean",
                "isolated_runtime_data_observed",
                "secrets_boundary_recorded",
                "routes_and_flags_recorded",
            )
        )
    if evidence_id == f"evidence-{W2LedgerItem.CROSS_FLAG_OFF.value}":
        subjects.append(f"ledger:{W2LedgerItem.CROSS_FLAG_OFF.value}")
    return json.dumps(
        {
            "schema": "live-voice.w2-automated-report.v2",
            "candidate_sha": _CANDIDATE_SHA,
            "suite_id": evidence_id,
            "passed_subjects": subjects,
        },
        sort_keys=True,
    ).encode()


def _assisted_subject(evidence_id: str) -> tuple[str, W2EvidenceKind, str]:
    if evidence_id == "gate1-review":
        return "review:gate1", W2EvidenceKind.INDEPENDENT_REVIEW, "gate1-automated"
    if evidence_id.startswith("showcase-") and evidence_id.endswith("-human"):
        number = evidence_id.split("-", 2)[1]
        return (
            f"showcase:{number}",
            W2EvidenceKind.HUMAN_OBSERVATION,
            evidence_id.removesuffix("-human") + "-runtime",
        )
    if evidence_id.startswith("journey-"):
        suffix = "-human" if evidence_id.endswith("-human") else "-fault"
        step = evidence_id.removeprefix("journey-").removesuffix(suffix)
        kind = (
            W2EvidenceKind.HUMAN_OBSERVATION
            if suffix == "-human"
            else W2EvidenceKind.FAULT_INJECTION
        )
        return f"journey:{step}", kind, "journey-runtime"
    if evidence_id.startswith("fault-") and evidence_id.endswith("-attestation"):
        core = evidence_id.removeprefix("fault-").removesuffix("-attestation")
        if core.endswith("-non-retriable"):
            plane = core.removesuffix("-non-retriable")
            fault_class = "non_retriable"
        elif core.endswith("-zero-effect"):
            plane = core.removesuffix("-zero-effect")
            fault_class = "zero_effect"
        else:
            plane = core.removesuffix("-retriable")
            fault_class = "retriable"
        return (
            f"fault:{plane}:{fault_class}",
            W2EvidenceKind.FAULT_INJECTION,
            evidence_id.removesuffix("-attestation") + "-runtime",
        )
    if evidence_id.startswith("evidence-") and evidence_id.endswith("-attestation"):
        runtime_id = evidence_id.removesuffix("-attestation")
        item = W2LedgerItem(runtime_id.removeprefix("evidence-"))
        kind = (
            W2EvidenceKind.HUMAN_OBSERVATION
            if item in {W2LedgerItem.P1_AUDIO, W2LedgerItem.P3_UI}
            else (
                W2EvidenceKind.FAULT_INJECTION
                if item is W2LedgerItem.CROSS_FAILURE
                else W2EvidenceKind.REAL_RUNTIME
            )
        )
        return f"ledger:{item.value}", kind, runtime_id
    raise AssertionError(f"unrecognized assisted evidence id: {evidence_id}")


def _restart_runtime_content() -> bytes:
    task_id = "task-restart-1"
    attempt_id = "attempt-restart-1"
    common = {
        "schema_version": OBSERVABILITY_SCHEMA_VERSION,
        "segment_name": "task.progress",
        "observed_at": "2026-08-07T20:00:00Z",
        "monotonic_ms": 1.0,
        "binding": {
            "correlation_id": "correlation-restart-1",
            "task_id": task_id,
            "attempt_id": attempt_id,
        },
        "route": _route("restart-1"),
        "source_component": "product.task_restart_recovery",
    }
    records = [
        create_observation(
            {
                **common,
                "event_id": "restart-route",
                "event_name": "route.selected",
            }
        ),
        create_observation(
            {
                **common,
                "event_id": "restart-complete",
                "event_name": "segment.completed",
                "source_record_id": "restart-complete-record",
                "state": "terminal",
                "outcome": "completed",
                "duration_ms": 1.0,
            }
        ),
        create_observation(
            {
                **common,
                "event_id": "restart-snapshot",
                "event_name": "task.state_observed",
                "source_event_id": "restart-snapshot-source",
                "source_occurred_at": "2026-08-07T20:00:00Z",
                "source_seq": 1,
                "state": "running",
            }
        ),
        create_observation(
            {
                **common,
                "event_id": "restart-reconciled",
                "event_name": "task.state_observed",
                "source_event_id": "restart-reconciled-source",
                "source_occurred_at": "2026-08-07T20:00:01Z",
                "source_seq": 2,
                "state": "terminal",
                "outcome": "completed",
            }
        ),
    ]
    return (
        "\n".join(
            json.dumps(
                {
                    "evidence_schema": "live-voice.w2-jsonl-evidence.v1",
                    "candidate": {
                        "candidate_sha": _CANDIDATE_SHA,
                        "environment_id": "environment-1",
                        "session_id": "session-1",
                        "mode_id": "integrated-formal",
                    },
                    "record_kind": "observation",
                    "sequence": sequence,
                    "record": record.to_dict(),
                },
                separators=(",", ":"),
                sort_keys=True,
            )
            for sequence, record in enumerate(records)
        )
        + "\n"
    ).encode()


def _artifact_for_id(
    evidence_id: str,
    sequence: int,
    *,
    environment_id: str = "environment-1",
    force_automated: bool = False,
) -> W2EvidenceArtifact:
    if evidence_id == "restart-1" and not force_automated:
        content = _restart_runtime_content()
        return verify_w2_runtime_jsonl_content(
            artifact_id=evidence_id,
            sequence=sequence,
            content=content,
            **_trust_args(
                W2EvidenceKind.REAL_RUNTIME,
                content,
                artifact_id=evidence_id,
                sequence=sequence,
            ),
        )
    assisted = (
        evidence_id.endswith("-human")
        or evidence_id.endswith("-fault")
        or evidence_id.endswith("-attestation")
        or evidence_id == "gate1-review"
    )
    runtime = None if force_automated or assisted else _runtime_spec(evidence_id)
    if runtime is not None:
        segment, fault, task_id = runtime
        content = _runtime_content(
            evidence_id,
            segment,
            fault=fault,
            task_id=task_id,
            environment_id=environment_id,
        )
        return verify_w2_runtime_jsonl_content(
            artifact_id=evidence_id,
            sequence=sequence,
            content=content,
            **_trust_args(
                W2EvidenceKind.REAL_RUNTIME,
                content,
                artifact_id=evidence_id,
                sequence=sequence,
            ),
        )
    if not force_automated and assisted:
        observed_subject, kind, runtime_id = _assisted_subject(evidence_id)
        receipt_type = {
            W2EvidenceKind.INDEPENDENT_REVIEW: "independent_review",
            W2EvidenceKind.FAULT_INJECTION: "fault_injection",
            W2EvidenceKind.HUMAN_OBSERVATION: "human_observation",
            W2EvidenceKind.REAL_RUNTIME: "runtime_attestation",
        }[kind]
        if runtime_id == "gate1-automated":
            observed_content = _automated_report(runtime_id)
        else:
            segment, fault, task_id = _runtime_spec(runtime_id)  # type: ignore[misc]
            observed_content = _runtime_content(
                runtime_id,
                segment,
                fault=fault,
                task_id=task_id,
            )
        content = _assisted_content(
            evidence_id,
            sequence,
            receipt_type,
            hashlib.sha256(observed_content).hexdigest(),
            observed_subject,
        )
        return verify_w2_assisted_receipt_content(
            content,
            **_trust_args(
                kind,
                content,
                artifact_id=evidence_id,
                sequence=sequence,
                artifact_kind="assisted_receipt",
            ),
        )
    content = _automated_report(evidence_id)
    return verify_w2_evidence_content(
        artifact_id=evidence_id,
        sequence=sequence,
        candidate_sha=_CANDIDATE_SHA,
        environment_id=environment_id,
        session_id="session-1",
        mode_id="integrated-formal",
        evidence_kinds=frozenset({W2EvidenceKind.AUTOMATED_CONFORMANCE}),
        source_label=f"automated-{sequence}",
        content=content,
        **_trust_args(
            W2EvidenceKind.AUTOMATED_CONFORMANCE,
            content,
            artifact_id=evidence_id,
            sequence=sequence,
            source_label=f"automated-{sequence}",
        ),
    )


def _reverify_artifact(
    artifact: W2EvidenceArtifact, **updates: object
) -> W2EvidenceArtifact:
    return _artifact_for_id(
        artifact.artifact_id,
        int(updates.get("sequence", artifact.sequence)),
        environment_id=str(updates.get("environment_id", artifact.environment_id)),
        force_automated=(
            updates.get("evidence_kinds")
            == frozenset({W2EvidenceKind.AUTOMATED_CONFORMANCE})
        ),
    )


def _evaluation_values() -> dict[str, object]:
    return {
        "candidate": _candidate(),
        "verification": _verification(),
        "awards": _awards(),
        "invariants": _invariants(),
        "showcase_runs": _runs(),
        "journey_steps": _journey(),
        "faults": _faults(),
        "restart": _restart(),
    }


def _evaluate(**overrides: object):
    values = _evaluation_values()
    artifacts = overrides.pop("artifacts", None)
    values.update(overrides)
    values["artifacts"] = _artifacts(values) if artifacts is None else artifacts
    return evaluate_w2_demo_gate(**values)  # type: ignore[arg-type]


def test_complete_candidate_record_passes_with_exact_section_totals() -> None:
    result = _evaluate()

    assert result.status is W2GateStatus.PASS
    assert result.total_score == 100
    assert result.section_scores == {
        W2Section.P1: 20,
        W2Section.P2: 40,
        W2Section.P3: 25,
        W2Section.CROSS_CUTTING: 15,
    }
    assert result.failures == ()
    with pytest.raises(TypeError):
        result.section_scores[W2Section.P1] = 0  # type: ignore[index]


def test_arbitrary_content_cannot_mint_runtime_human_or_review_truth() -> None:
    for kind in (
        W2EvidenceKind.REAL_RUNTIME,
        W2EvidenceKind.HUMAN_OBSERVATION,
        W2EvidenceKind.INDEPENDENT_REVIEW,
    ):
        with pytest.raises(W2GateContractViolation, match="only prove automated"):
            content = b"caller-selected bytes"
            verify_w2_evidence_content(
                artifact_id=f"forged-{kind.value}",
                sequence=1,
                candidate_sha=_CANDIDATE_SHA,
                environment_id="environment-1",
                session_id="session-1",
                mode_id="integrated-formal",
                evidence_kinds=frozenset({kind}),
                source_label="caller-asserted",
                content=content,
                **_trust_args(
                    W2EvidenceKind.AUTOMATED_CONFORMANCE,
                    content,
                    artifact_id=f"forged-{kind.value}",
                    sequence=1,
                    source_label="caller-asserted",
                ),
            )
    invalid_runtime = b"caller-selected bytes"
    with pytest.raises(W2GateContractViolation, match="invalid JSON"):
        verify_w2_runtime_jsonl_content(
            artifact_id="forged-runtime",
            sequence=1,
            content=invalid_runtime,
            **_trust_args(
                W2EvidenceKind.REAL_RUNTIME,
                invalid_runtime,
                artifact_id="forged-runtime",
                sequence=1,
            ),
        )
    invalid_automated = b"caller-selected bytes"
    with pytest.raises(W2GateContractViolation, match="closed report"):
        verify_w2_evidence_content(
            artifact_id="forged-automated",
            sequence=1,
            candidate_sha=_CANDIDATE_SHA,
            environment_id="environment-1",
            session_id="session-1",
            mode_id="integrated-formal",
            evidence_kinds=frozenset({W2EvidenceKind.AUTOMATED_CONFORMANCE}),
            source_label="caller-asserted",
            content=invalid_automated,
            **_trust_args(
                W2EvidenceKind.AUTOMATED_CONFORMANCE,
                invalid_automated,
                artifact_id="forged-automated",
                sequence=1,
                source_label="caller-asserted",
            ),
        )


def test_runtime_failure_needs_a_separate_fault_attestation() -> None:
    content = _runtime_content("ordinary-failure", "agent.dispatch", fault=True)
    runtime = verify_w2_runtime_jsonl_content(
        artifact_id="ordinary-failure",
        sequence=1,
        content=content,
        **_trust_args(
            W2EvidenceKind.REAL_RUNTIME,
            content,
            artifact_id="ordinary-failure",
            sequence=1,
        ),
    )
    receipt_content = _assisted_content(
        "ordinary-failure-attestation",
        2,
        "fault_injection",
        runtime.content_sha256,
        "fault:p2.conversation:retriable",
    )
    receipt = verify_w2_assisted_receipt_content(
        receipt_content,
        **_trust_args(
            W2EvidenceKind.FAULT_INJECTION,
            receipt_content,
            artifact_id="ordinary-failure-attestation",
            sequence=2,
        ),
    )

    assert runtime.evidence_kinds == frozenset({W2EvidenceKind.REAL_RUNTIME})
    assert receipt.evidence_kinds == frozenset({W2EvidenceKind.FAULT_INJECTION})
    assert receipt.attested_content_sha256 == frozenset({runtime.content_sha256})


def test_runtime_evidence_rejects_unsigned_wrong_role_and_tampered_content() -> None:
    content = _runtime_content("trust-bound-runtime", "runtime.turn")
    valid = _trust_args(
        W2EvidenceKind.REAL_RUNTIME,
        content,
        artifact_id="tampered-runtime",
        sequence=1,
    )
    with pytest.raises(W2GateContractViolation, match="signature is invalid"):
        verify_w2_runtime_jsonl_content(
            artifact_id="unsigned-runtime",
            sequence=1,
            content=content,
            trust_policy=_TRUST_POLICY,
            signer_id=_SIGNERS[W2EvidenceKind.REAL_RUNTIME],
            signature_hex="",
        )
    with pytest.raises(W2GateContractViolation, match="not trusted for this role"):
        verify_w2_runtime_jsonl_content(
            artifact_id="wrong-role-runtime",
            sequence=1,
            content=content,
            **_trust_args(
                W2EvidenceKind.HUMAN_OBSERVATION,
                content,
                artifact_id="wrong-role-runtime",
                sequence=1,
            ),
        )
    with pytest.raises(W2GateContractViolation, match="verification failed"):
        verify_w2_runtime_jsonl_content(
            artifact_id="tampered-runtime",
            sequence=1,
            content=content + b" ",
            **valid,
        )


def test_v2_runtime_identity_producer_footer_and_marker_sources_fail_closed() -> None:
    artifact_id = "agentserver-v2-1"
    sequence = 1
    legacy = _runtime_content("valid-agentserver-v2", "runtime.turn")
    content = _v2_runtime_content(
        legacy,
        artifact_id=artifact_id,
        artifact_sequence=sequence,
    )
    artifact = verify_w2_runtime_jsonl_content(
        artifact_id=artifact_id,
        sequence=sequence,
        content=content,
        **_trust_args(
            W2EvidenceKind.REAL_RUNTIME,
            content,
            artifact_id=artifact_id,
            sequence=sequence,
        ),
    )
    assert artifact.runtime_format_version == 2
    assert artifact.evidence_set_id == "evidence-set-1"
    assert artifact.producer_id == "agentserver"
    assert artifact.process_epoch == "agentserver-epoch-1"
    assert artifact.proven_ledger_items == frozenset()

    wrong_producer = _v2_runtime_content(
        legacy,
        artifact_id="gateway-v2-1",
        artifact_sequence=3,
        producer_id="gateway",
    )
    with pytest.raises(W2GateContractViolation, match="producer"):
        verify_w2_runtime_jsonl_content(
            artifact_id="gateway-v2-1",
            sequence=3,
            content=wrong_producer,
            **_trust_args(
                W2EvidenceKind.REAL_RUNTIME,
                wrong_producer,
                artifact_id="gateway-v2-1",
                sequence=3,
            ),
        )

    wrong_identity = _v2_runtime_content(
        legacy,
        artifact_id="different-artifact",
        artifact_sequence=sequence,
    )
    with pytest.raises(W2GateContractViolation, match="identity"):
        verify_w2_runtime_jsonl_content(
            artifact_id=artifact_id,
            sequence=sequence,
            content=wrong_identity,
            **_trust_args(
                W2EvidenceKind.REAL_RUNTIME,
                wrong_identity,
                artifact_id=artifact_id,
                sequence=sequence,
            ),
        )

    marker = _v2_runtime_content(
        _runtime_content("showcase-1-runtime", "runtime.turn"),
        artifact_id="marker-artifact",
        artifact_sequence=2,
    )
    with pytest.raises(W2GateContractViolation, match="marker"):
        verify_w2_runtime_jsonl_content(
            artifact_id="marker-artifact",
            sequence=2,
            content=marker,
            **_trust_args(
                W2EvidenceKind.REAL_RUNTIME,
                marker,
                artifact_id="marker-artifact",
                sequence=2,
            ),
        )


def test_v2_fault_classes_are_derived_from_exact_failure_facts() -> None:
    retriable = _v2_failure_artifact(
        artifact_id="p1-retriable-v2",
        artifact_sequence=1,
        segment_name="speech.recognition",
        reason_code="TIMEOUT",
        error_code="TIMEOUT",
    )
    non_retriable = _v2_failure_artifact(
        artifact_id="p1-non-retriable-v2",
        artifact_sequence=2,
        segment_name="speech.recognition",
        reason_code="PROTOCOL_REJECTED",
        error_code="INVALID_ARGUMENT",
    )
    zero_effect = _v2_failure_artifact(
        artifact_id="p1-stale-v2",
        artifact_sequence=3,
        segment_name="speech.recognition",
        reason_code="PROTOCOL_REJECTED",
        error_code="STALE",
    )

    assert _derive_v2_fault_class(
        (retriable,),
        plane=W2CapabilityPlane.P1_SPEECH_MEDIA,
        fault_class="retriable",
    )
    assert _derive_v2_fault_class(
        (non_retriable,),
        plane=W2CapabilityPlane.P1_SPEECH_MEDIA,
        fault_class="non_retriable",
    )
    assert _derive_v2_fault_class(
        (zero_effect,),
        plane=W2CapabilityPlane.P1_SPEECH_MEDIA,
        fault_class="zero_effect",
    )
    assert not _derive_v2_fault_class(
        (retriable,),
        plane=W2CapabilityPlane.P3_TASK,
        fault_class="retriable",
    )
    assert not _derive_v2_fault_class(
        (zero_effect,),
        plane=W2CapabilityPlane.OBSERVABILITY,
        fault_class="zero_effect",
    )


def test_v2_journey_requires_one_time_ordered_cross_producer_causal_chain() -> None:
    by_producer: dict[str, list[object]] = {"gateway": [], "agentserver": []}
    sequence = 0

    def observed_at(second: int) -> str:
        return f"2026-08-07T20:00:{second:02d}Z"

    def append_completed(
        producer: str,
        source: str,
        segment: str,
        binding: dict[str, object],
        second: int,
    ) -> None:
        nonlocal sequence
        record_id = f"record-{sequence}"
        common = {
            "schema_version": OBSERVABILITY_SCHEMA_VERSION,
            "segment_name": segment,
            "observed_at": observed_at(second),
            "monotonic_ms": float(sequence + 1),
            "binding": {"correlation_id": "correlation-journey", **binding},
            "route": _route("v2-journey"),
            "source_component": source,
            "source_record_id": record_id,
        }
        by_producer[producer].extend(
            (
                create_observation(
                    {
                        **common,
                        "event_id": f"route-{sequence}",
                        "event_name": "route.selected",
                    }
                ),
                create_observation(
                    {
                        **common,
                        "event_id": f"complete-{sequence}",
                        "event_name": "segment.completed",
                        "state": "terminal",
                        "outcome": "completed",
                        "duration_ms": 1.0,
                    }
                ),
            )
        )
        sequence += 1

    append_completed(
        "gateway",
        "product.w2.speech.recognize",
        "speech.recognition",
        {"interaction_id": "interaction-1"},
        1,
    )
    append_completed(
        "agentserver",
        "product.w2.p2.submit.agent",
        "agent.dispatch",
        {
            "interaction_id": "interaction-1",
            "response_id": "response-1",
            "response_generation": 0,
            "round_id": "round-1",
        },
        2,
    )
    for second, source in (
        (3, "product.w2.agent.tool_call"),
        (4, "product.w2.agent.tool_result"),
        (5, "product.w2.agent.final"),
    ):
        append_completed(
            "agentserver",
            source,
            "agent.progress",
            {"round_id": "round-1"},
            second,
        )
    append_completed(
        "gateway",
        "product.w2.speech.synthesize",
        "speech.synthesis",
        {
            "interaction_id": "interaction-1",
            "response_id": "response-1",
            "response_generation": 0,
        },
        7,
    )
    append_completed(
        "agentserver",
        "product.w2.p2.presentation",
        "runtime.presentation",
        {
            "interaction_id": "interaction-1",
            "response_id": "response-1",
            "response_generation": 0,
        },
        6,
    )
    append_completed(
        "agentserver",
        "product.w2.p2.submit.agent",
        "agent.dispatch",
        {
            "interaction_id": "interaction-2",
            "response_id": "response-2",
            "response_generation": 0,
            "round_id": "round-2",
        },
        8,
    )
    by_producer["agentserver"].append(
        create_observation(
            {
                "schema_version": OBSERVABILITY_SCHEMA_VERSION,
                "event_id": "barge-2",
                "event_name": "cancel.acknowledged",
                "segment_name": "speech.playout",
                "observed_at": observed_at(9),
                "monotonic_ms": 9.0,
                "binding": {
                    "correlation_id": "correlation-journey",
                    "interaction_id": "interaction-2",
                    "response_id": "response-2",
                    "response_generation": 0,
                },
                "route": _route("v2-journey"),
                "source_component": "product.w2.p2.barge",
                "source_record_id": "barge-record-2",
                "reason_code": "CANCEL_ACKNOWLEDGED",
                "cancel_scope": "playback.stop",
            }
        )
    )
    task_binding = {"task_id": "task-journey", "attempt_id": "attempt-journey"}
    append_completed(
        "agentserver",
        "product.voice_task_origin",
        "runtime.turn",
        {
            "interaction_id": "interaction-3",
            "turn_id": "turn-3",
            **task_binding,
        },
        10,
    )
    append_completed(
        "agentserver",
        "product.w2.task.create",
        "task.command",
        task_binding,
        11,
    )
    append_completed(
        "agentserver",
        "product.voice_task_bridge",
        "task.command",
        {
            "interaction_id": "interaction-3",
            "turn_id": "turn-3",
            **task_binding,
        },
        12,
    )

    def append_task_state(second: int, state: str, outcome: str | None) -> None:
        by_producer["agentserver"].append(
            create_observation(
                {
                    "schema_version": OBSERVABILITY_SCHEMA_VERSION,
                    "event_id": f"task-state-{second}",
                    "event_name": "task.state_observed",
                    "segment_name": "task.progress",
                    "observed_at": observed_at(second),
                    "monotonic_ms": float(second),
                    "binding": {
                        "correlation_id": "correlation-journey",
                        **task_binding,
                    },
                    "route": _route("v2-journey"),
                    "source_component": "product.w2.task.event",
                    "source_event_id": f"task-event-{second}",
                    "source_occurred_at": observed_at(second),
                    "source_seq": second,
                    "state": state,
                    "outcome": outcome,
                }
            )
        )

    append_task_state(13, "running", None)
    append_completed(
        "agentserver",
        "product.w2.p2.submit.agent",
        "agent.dispatch",
        {
            "interaction_id": "interaction-4",
            "round_id": "round-4",
            **task_binding,
        },
        14,
    )
    append_task_state(15, "terminal", "completed")
    for second, source in (
        (16, "product.w2.task.status"),
        (17, "product.w2.task.events"),
        (18, "product.w2.p3.progress"),
        (19, "product.w2.p3.ui"),
    ):
        append_completed("agentserver", source, "task.progress", task_binding, second)
    by_producer["gateway"].append(
        create_observation(
            {
                "schema_version": OBSERVABILITY_SCHEMA_VERSION,
                "event_id": "speech-failure-20",
                "event_name": "segment.failed",
                "segment_name": "speech.recognition",
                "observed_at": observed_at(20),
                "monotonic_ms": 20.0,
                "binding": {
                    "correlation_id": "correlation-journey",
                    "interaction_id": "interaction-5",
                },
                "route": _route("v2-journey"),
                "source_component": "product.w2.speech.recognize",
                "source_record_id": "speech-failure-record-20",
                "state": "failed",
                "outcome": "failed",
                "reason_code": "PROVIDER_FAILURE",
                "error_code": "INTERNAL",
                "duration_ms": 1.0,
            }
        )
    )
    append_completed(
        "agentserver",
        "product.w2.p2.submit.agent",
        "agent.dispatch",
        {"interaction_id": "interaction-5", "round_id": "round-5"},
        21,
    )
    append_completed(
        "gateway",
        "product.w2.speech.synthesize",
        "speech.synthesis",
        {
            "interaction_id": "interaction-6",
            "response_id": "response-6",
            "response_generation": 0,
        },
        22,
    )
    append_completed(
        "agentserver",
        "product.w2.p2.presentation",
        "runtime.presentation",
        {
            "interaction_id": "interaction-6",
            "response_id": "response-6",
            "response_generation": 0,
        },
        23,
    )

    artifacts = []
    for artifact_sequence, producer in enumerate(("gateway", "agentserver"), 1):
        envelopes = [
            {
                "evidence_schema": "live-voice.w2-jsonl-evidence.v1",
                "candidate": {
                    "candidate_sha": _CANDIDATE_SHA,
                    "environment_id": "environment-1",
                    "session_id": "session-1",
                    "mode_id": "integrated-formal",
                },
                "record_kind": "observation",
                "sequence": record_sequence,
                "record": record.to_dict(),
            }
            for record_sequence, record in enumerate(by_producer[producer])
        ]
        legacy = ("\n".join(json.dumps(item) for item in envelopes) + "\n").encode()
        artifact_id = f"{producer}-ordered-journey"
        content = _v2_runtime_content(
            legacy,
            artifact_id=artifact_id,
            artifact_sequence=artifact_sequence,
            producer_id=producer,
            process_epoch=f"{producer}-ordered-journey-epoch",
        )
        artifacts.append(
            verify_w2_runtime_jsonl_content(
                artifact_id=artifact_id,
                sequence=artifact_sequence,
                content=content,
                **_runtime_trust_args(
                    content,
                    artifact_id=artifact_id,
                    sequence=artifact_sequence,
                    producer_id=producer,
                ),
            )
        )

    derivation = _derive_v2_journey_steps(tuple(artifacts))
    assert derivation.steps == frozenset(W2JourneyStep)
    assert derivation.full_chain_correlations == frozenset({"correlation-journey"})
    assert derivation.full_chain_task_ids == frozenset({"task-journey"})


def test_v2_restart_requires_linked_epochs_and_exact_task_attempt_sequence() -> None:
    before = _v2_task_state_artifact(
        artifact_id="agentserver-before-restart",
        artifact_sequence=1,
        process_epoch="agentserver-epoch-before",
        source_seq=10,
        state="running",
        outcome=None,
    )
    after = _v2_task_state_artifact(
        artifact_id="agentserver-after-restart",
        artifact_sequence=2,
        process_epoch="agentserver-epoch-after",
        predecessor_artifact_id=before.artifact_id,
        source_seq=11,
        state="terminal",
        outcome="interrupted",
    )

    assert _derive_v2_restart((before, after)) == {
        "task-restart-v2": W2ReconciliationOutcome.INTERRUPTED
    }
    assert _derive_v2_restart((after,)) == {}


def test_v2_restart_uses_each_tasks_latest_unique_predecessor_state() -> None:
    before, after = _v2_restart_pair(
        (
            ("task-x", "attempt-old", 1, "running", None),
            ("task-x", "attempt-old", 2, "terminal", "completed"),
            ("task-x", "attempt-current", 3, "running", None),
        ),
        (("task-x", "attempt-current", 4, "terminal", "interrupted"),),
    )

    details = _derive_v2_restart_details((before, after))

    assert details.valid_artifact_pairs == frozenset(
        {(before.artifact_id, after.artifact_id)}
    )
    assert details.tasks == {"task-x": W2ReconciliationOutcome.INTERRUPTED}
    assert details.attempts_by_task == {"task-x": "attempt-current"}
    assert details.diagnostics == ()


def test_v2_restart_rejects_duplicate_latest_predecessor_without_erasing_peer() -> None:
    before, after = _v2_restart_pair(
        (
            ("task-x", "attempt-x", 1, "running", None),
            ("task-x", "attempt-x", 1, "running", None),
            ("task-y", "attempt-y", 1, "running", None),
        ),
        (
            ("task-x", "attempt-x", 2, "terminal", "interrupted"),
            ("task-y", "attempt-y", 2, "terminal", "interrupted"),
        ),
    )

    details = _derive_v2_restart_details((before, after))

    assert details.tasks == {"task-y": W2ReconciliationOutcome.INTERRUPTED}
    assert "predecessor_latest_duplicate:task-x:1" in details.diagnostics


@pytest.mark.parametrize(
    ("successor_facts", "diagnostic", "expected_tasks"),
    (
        (
            (("task-y", "attempt-y", 2, "terminal", "interrupted"),),
            "successor_missing:task-x:attempt-x",
            {"task-y": W2ReconciliationOutcome.INTERRUPTED},
        ),
        (
            (
                ("task-x", "attempt-x", 2, "terminal", "interrupted"),
                ("task-y", "attempt-y", 2, "terminal", "interrupted"),
                ("task-z", "attempt-z", 2, "terminal", "interrupted"),
            ),
            "successor_extra:task-z:attempt-z",
            {
                "task-x": W2ReconciliationOutcome.INTERRUPTED,
                "task-y": W2ReconciliationOutcome.INTERRUPTED,
            },
        ),
    ),
    ids=("missing", "extra"),
)
def test_v2_restart_requires_exact_successor_task_attempt_set(
    successor_facts: tuple[tuple[str, str, int, str, str | None], ...],
    diagnostic: str,
    expected_tasks: dict[str, W2ReconciliationOutcome],
) -> None:
    before, after = _v2_restart_pair(
        (
            ("task-x", "attempt-x", 1, "running", None),
            ("task-y", "attempt-y", 1, "running", None),
        ),
        successor_facts,
    )

    details = _derive_v2_restart_details((before, after))

    assert details.tasks == expected_tasks
    assert diagnostic in details.diagnostics
    assert _derive_v2_restart((before, after)) == expected_tasks


@pytest.mark.parametrize(
    ("task_x_facts", "diagnostic"),
    (
        (
            (
                ("task-x", "attempt-x", 2, "terminal", "interrupted"),
                ("task-x", "attempt-x", 2, "terminal", "interrupted"),
            ),
            "successor_duplicate:task-x:attempt-x",
        ),
        (
            (
                ("task-x", "attempt-x", 2, "terminal", "interrupted"),
                ("task-x", "attempt-x", 2, "terminal", "completed"),
            ),
            "successor_raw_outcome_conflict:task-x:attempt-x",
        ),
        (
            (("task-x", "attempt-x", 1, "terminal", "interrupted"),),
            "task_seq_not_advanced:task-x:attempt-x:1:1",
        ),
        (
            (
                ("task-x", "attempt-x", 2, "terminal", "interrupted"),
                ("task-x", "attempt-other", 2, "terminal", "interrupted"),
            ),
            "successor_multiple_attempts:task-x",
        ),
    ),
    ids=("duplicate-same-outcome", "outcome-conflict", "seq", "multiple-attempts"),
)
def test_v2_restart_conflict_on_task_x_preserves_valid_task_y_and_diagnostic(
    task_x_facts: tuple[tuple[str, str, int, str, str | None], ...],
    diagnostic: str,
) -> None:
    before, after = _v2_restart_pair(
        (
            ("task-x", "attempt-x", 1, "running", None),
            ("task-y", "attempt-y", 1, "running", None),
        ),
        (
            *task_x_facts,
            ("task-y", "attempt-y", 2, "terminal", "interrupted"),
        ),
    )

    details = _derive_v2_restart_details((before, after))

    assert details.tasks == {"task-y": W2ReconciliationOutcome.INTERRUPTED}
    assert details.attempts_by_task == {"task-y": "attempt-y"}
    assert diagnostic in details.diagnostics
    assert _derive_v2_restart((before, after)) == {
        "task-y": W2ReconciliationOutcome.INTERRUPTED
    }


def test_v2_restart_diagnostic_always_fails_the_evaluator() -> None:
    values = _evaluation_values()
    base_artifacts = _artifacts(values)
    before, after = _v2_restart_pair(
        (("task-x", "attempt-x", 1, "running", None),),
        (
            ("task-x", "attempt-x", 2, "terminal", "interrupted"),
            ("task-x", "attempt-x", 2, "terminal", "interrupted"),
        ),
        artifact_sequence_start=len(base_artifacts) + 1,
        artifact_prefix="agentserver-diagnostic",
    )

    result = evaluate_w2_demo_gate(
        **values, artifacts=(*base_artifacts, before, after)  # type: ignore[arg-type]
    )

    assert result.status is W2GateStatus.FAIL
    assert (
        "restart evidence diagnostic: successor_duplicate:task-x:attempt-x"
        in result.failures
    )


def test_v2_core_cancel_and_executor_require_full_ordered_abc_retry_truth() -> None:
    before, after = _v2_abc_retry_artifacts()

    proven = _derive_v2_runtime_items((before, after))
    restart = _derive_v2_restart_details((before, after))

    assert W2LedgerItem.P3_CORE in proven
    assert W2LedgerItem.P3_EXECUTOR in proven
    assert restart.tasks == {
        "task-abc": W2ReconciliationOutcome.INTERRUPTED,
    }
    assert restart.attempts_by_task == {"task-abc": "attempt-c"}
    assert restart.valid_task_attempt_pairs == frozenset(
        {("task-abc", "attempt-c")}
    )
    assert restart.diagnostics == ()


def test_v2_core_cancel_allows_events_query_after_cancelled_terminal() -> None:
    before, after = _v2_abc_retry_artifacts()
    records = before.runtime_observations
    terminal_index = next(
        index
        for index, item in enumerate(records)
        if item.source_component == "product.w2.task.event"
        and item.outcome == "cancelled"
    )
    events_index = next(
        index
        for index, item in enumerate(records)
        if item.source_component == "product.w2.task.events"
        and item.event_name == "segment.completed"
    )

    assert terminal_index < events_index
    assert W2LedgerItem.P3_CORE in _derive_v2_runtime_items((before, after))


@pytest.mark.parametrize(
    "overrides",
    (
        {"cancel_attempt": "attempt-wrong"},
        {"include_cancel_command": False},
        {"cancel_outcome": None},
        {"cancel_outcome": "completed"},
        {"cancel_terminal_before_command": True},
    ),
    ids=(
        "wrong-attempt",
        "missing-cancel-command",
        "missing-terminal",
        "wrong-outcome",
        "wrong-order",
    ),
)
def test_v2_core_cancel_requires_exact_attempt_cancelled_terminal_after_command(
    overrides: dict[str, object],
) -> None:
    artifacts = _v2_abc_retry_artifacts(**overrides)  # type: ignore[arg-type]

    proven = _derive_v2_runtime_items(artifacts)

    assert W2LedgerItem.P3_CORE not in proven
    assert W2LedgerItem.P3_EXECUTOR not in proven


@pytest.mark.parametrize(
    "overrides",
    (
        {"d0_attempt": "attempt-c"},
        {"retry_attempts": ("attempt-b",)},
        {"retry_attempts": ("attempt-b", "attempt-b")},
        {"execution_order": "d0_before_retry"},
        {"execution_order": "second_retry_before_d0"},
        {"extra_retry_attempt": "attempt-d"},
    ),
    ids=(
        "wrong-d0-attempt",
        "only-one-retry",
        "retry-b-equals-retry-c",
        "d0-before-retry-b",
        "retry-c-before-d0-b",
        "extra-fourth-attempt",
    ),
)
def test_v2_executor_rejects_incomplete_or_misordered_abc_retry_topology(
    overrides: dict[str, object],
) -> None:
    artifacts = _v2_abc_retry_artifacts(**overrides)  # type: ignore[arg-type]

    proven = _derive_v2_runtime_items(artifacts)

    assert W2LedgerItem.P3_CORE in proven
    assert W2LedgerItem.P3_EXECUTOR not in proven


def test_v2_cross_file_merge_uses_producer_and_full_binding_not_correlation() -> None:
    contents: list[bytes] = []
    for subject, segment_name in (
        ("gateway-capture", "speech.capture"),
        ("agentserver-presentation", "runtime.presentation"),
    ):
        envelopes = [
            json.loads(line)
            for line in _runtime_content(subject, segment_name).decode().splitlines()
        ]
        for envelope in envelopes:
            envelope["record"]["binding"]["correlation_id"] = "same-correlation"
            envelope["record"]["binding"]["interaction_id"] = "interaction-cross"
        contents.append(
            ("\n".join(json.dumps(item) for item in envelopes) + "\n").encode()
        )
    gateway_content = _v2_runtime_content(
        contents[0],
        artifact_id="gateway-cross-file",
        artifact_sequence=1,
        producer_id="gateway",
        process_epoch="gateway-epoch-cross-file",
    )
    agentserver_content = _v2_runtime_content(
        contents[1],
        artifact_id="agentserver-cross-file",
        artifact_sequence=2,
        process_epoch="agentserver-epoch-cross-file",
    )
    gateway = verify_w2_runtime_jsonl_content(
        artifact_id="gateway-cross-file",
        sequence=1,
        content=gateway_content,
        **_runtime_trust_args(
            gateway_content,
            artifact_id="gateway-cross-file",
            sequence=1,
            producer_id="gateway",
        ),
    )
    agentserver = verify_w2_runtime_jsonl_content(
        artifact_id="agentserver-cross-file",
        sequence=2,
        content=agentserver_content,
        **_runtime_trust_args(
            agentserver_content,
            artifact_id="agentserver-cross-file",
            sequence=2,
            producer_id="agentserver",
        ),
    )

    proven = _derive_v2_runtime_items((gateway, agentserver))
    assert W2LedgerItem.CROSS_OBSERVABILITY in proven
    assert W2LedgerItem.P1_AUDIO not in proven
    assert W2LedgerItem.P2_MEDIA not in proven
    assert json.loads(gateway_content.decode().splitlines()[1])["sequence"] == 0
    assert json.loads(agentserver_content.decode().splitlines()[1])["sequence"] == 0


def test_v2_rejects_gateway_source_signed_by_agentserver() -> None:
    legacy = _runtime_content("wrong-source-owner", "speech.recognition")
    envelopes = [json.loads(line) for line in legacy.decode().splitlines()]
    for envelope in envelopes:
        envelope["record"]["source_component"] = "product.w2.speech.recognize"
    legacy = ("\n".join(json.dumps(item) for item in envelopes) + "\n").encode()
    content = _v2_runtime_content(
        legacy,
        artifact_id="wrong-source-owner",
        artifact_sequence=1,
        producer_id="agentserver",
    )
    with pytest.raises(W2GateContractViolation, match="signed producer"):
        verify_w2_runtime_jsonl_content(
            artifact_id="wrong-source-owner",
            sequence=1,
            content=content,
            **_runtime_trust_args(
                content,
                artifact_id="wrong-source-owner",
                sequence=1,
                producer_id="agentserver",
            ),
        )


def test_v2_same_correlation_with_different_interaction_is_not_cross_proof() -> None:
    artifacts = []
    for index, (subject, segment, producer) in enumerate(
        (
            ("gateway-different-interaction", "speech.capture", "gateway"),
            (
                "agentserver-different-interaction",
                "runtime.presentation",
                "agentserver",
            ),
        ),
        start=1,
    ):
        envelopes = [
            json.loads(line)
            for line in _runtime_content(subject, segment).decode().splitlines()
        ]
        for envelope in envelopes:
            envelope["record"]["binding"]["correlation_id"] = "same-correlation"
        legacy = ("\n".join(json.dumps(item) for item in envelopes) + "\n").encode()
        content = _v2_runtime_content(
            legacy,
            artifact_id=subject,
            artifact_sequence=index,
            producer_id=producer,
        )
        artifacts.append(
            verify_w2_runtime_jsonl_content(
                artifact_id=subject,
                sequence=index,
                content=content,
                **_runtime_trust_args(
                    content,
                    artifact_id=subject,
                    sequence=index,
                    producer_id=producer,
                ),
            )
        )
    assert W2LedgerItem.CROSS_OBSERVABILITY not in _derive_v2_runtime_items(
        tuple(artifacts)
    )


def test_v2_stale_failure_plus_same_request_completion_is_not_zero_effect() -> None:
    failed_lines = [
        json.loads(line)
        for line in _runtime_content(
            "stale-with-effect", "speech.recognition", fault=True
        )
        .decode()
        .splitlines()
    ]
    success_lines = [
        json.loads(line)
        for line in _runtime_content("stale-with-effect-success", "speech.recognition")
        .decode()
        .splitlines()
    ]
    failed = failed_lines[0]["record"]
    failed["reason_code"] = "PROTOCOL_REJECTED"
    failed["error_code"] = "STALE"
    for envelope in (*failed_lines, *success_lines):
        envelope["record"]["binding"]["correlation_id"] = "same-fault-request"
        envelope["record"]["binding"]["interaction_id"] = "interaction-fault"
    completed = next(
        envelope["record"]
        for envelope in success_lines
        if envelope["record"]["event_name"] == "segment.completed"
    )
    completed["source_record_id"] = failed["source_record_id"]
    records = [*failed_lines, *success_lines]
    for sequence, envelope in enumerate(records):
        envelope["sequence"] = sequence
    legacy = ("\n".join(json.dumps(item) for item in records) + "\n").encode()
    content = _v2_runtime_content(
        legacy,
        artifact_id="stale-with-effect",
        artifact_sequence=1,
        producer_id="gateway",
    )
    artifact = verify_w2_runtime_jsonl_content(
        artifact_id="stale-with-effect",
        sequence=1,
        content=content,
        **_runtime_trust_args(
            content,
            artifact_id="stale-with-effect",
            sequence=1,
            producer_id="gateway",
        ),
    )
    assert not _derive_v2_fault_class(
        (artifact,),
        plane=W2CapabilityPlane.P1_SPEECH_MEDIA,
        fault_class="zero_effect",
    )


def test_v2_p3_stale_retry_is_independent_of_completed_task_create() -> None:
    create_lines = [
        json.loads(line)
        for line in _runtime_content(
            "p3-create-before-stale-retry",
            "task.command",
            task_id="task-stale-retry",
        )
        .decode()
        .splitlines()
    ]
    stale_lines = [
        json.loads(line)
        for line in _runtime_content(
            "p3-stale-retry",
            "task.command",
            fault=True,
            task_id="task-stale-retry",
        )
        .decode()
        .splitlines()
    ]
    correlation_id = "correlation-p3-stale-retry"
    for envelope in (*create_lines, *stale_lines):
        record = envelope["record"]
        record["binding"]["correlation_id"] = correlation_id
    failed = stale_lines[0]["record"]
    failed["source_component"] = "product.w2.task.retry"
    failed["reason_code"] = "PROTOCOL_REJECTED"
    failed["error_code"] = "STALE"
    records = [*create_lines, *stale_lines]
    for sequence, envelope in enumerate(records):
        envelope["sequence"] = sequence
    content = _v2_runtime_content(
        ("\n".join(json.dumps(item) for item in records) + "\n").encode(),
        artifact_id="p3-stale-retry",
        artifact_sequence=1,
        producer_id="agentserver",
    )
    artifact = verify_w2_runtime_jsonl_content(
        artifact_id="p3-stale-retry",
        sequence=1,
        content=content,
        **_runtime_trust_args(
            content,
            artifact_id="p3-stale-retry",
            sequence=1,
            producer_id="agentserver",
        ),
    )

    assert _derive_v2_fault_class(
        (artifact,),
        plane=W2CapabilityPlane.P3_TASK,
        fault_class="zero_effect",
    )


def test_v2_capture_and_synthesis_without_playout_earn_no_audio_credit() -> None:
    content = _v2_runtime_content(
        _runtime_content("no-browser-playout", ("speech.capture", "speech.synthesis")),
        artifact_id="no-browser-playout",
        artifact_sequence=1,
        producer_id="gateway",
    )
    artifact = verify_w2_runtime_jsonl_content(
        artifact_id="no-browser-playout",
        sequence=1,
        content=content,
        **_runtime_trust_args(
            content,
            artifact_id="no-browser-playout",
            sequence=1,
            producer_id="gateway",
        ),
    )
    assert W2LedgerItem.P1_AUDIO not in _derive_v2_runtime_items((artifact,))


def test_v2_sequential_bounded_playout_receipt_cannot_mint_duplex_media() -> None:
    legacy = _runtime_content(
        "sequential-bounded-media",
        ("speech.capture", "speech.playout"),
    )
    envelopes = [json.loads(line) for line in legacy.decode().splitlines()]
    sources = {
        "speech.capture": "product.w2.media.capture",
        "speech.playout": "product.w2.browser.playout",
    }
    for envelope in envelopes:
        record = envelope["record"]
        segment = record["segment_name"]
        record["source_component"] = sources[segment]
        binding = record["binding"]
        binding["correlation_id"] = "correlation-sequential-media"
        binding["interaction_id"] = "interaction-sequential-media"
        if segment == "speech.playout":
            binding["response_id"] = "response-sequential-media"
            binding["response_generation"] = 1
            record["source_record_id"] = "same-browser-receipt"
    legacy = ("\n".join(json.dumps(item) for item in envelopes) + "\n").encode()
    content = _v2_runtime_content(
        legacy,
        artifact_id="sequential-bounded-media",
        artifact_sequence=1,
        producer_id="gateway",
    )
    artifact = verify_w2_runtime_jsonl_content(
        artifact_id="sequential-bounded-media",
        sequence=1,
        content=content,
        **_runtime_trust_args(
            content,
            artifact_id="sequential-bounded-media",
            sequence=1,
            producer_id="gateway",
        ),
    )

    proven = _derive_v2_runtime_items((artifact,))
    assert W2LedgerItem.P1_AUDIO in proven
    assert W2LedgerItem.P2_MEDIA not in proven


def test_v2_exact_downlink_playout_overlap_and_later_capture_mint_duplex_media() -> (
    None
):
    legacy = _runtime_content(
        "real-duplex-media",
        (
            "speech.capture",
            "runtime.queue",
            "speech.playout",
            "runtime.queue",
            "speech.capture",
        ),
    )
    envelopes = [json.loads(line) for line in legacy.decode().splitlines()]
    queue_index = 0
    for envelope in envelopes:
        record = envelope["record"]
        segment = record["segment_name"]
        binding = record["binding"]
        binding["correlation_id"] = "correlation-duplex-media"
        binding["interaction_id"] = "interaction-duplex-media"
        if segment == "runtime.queue":
            source = (
                "product.w2.media.downlink"
                if queue_index < 2
                else "product.w2.media.duplex"
            )
            # Each logical fact has route.selected plus segment.completed.
            if record["event_name"] == "segment.completed":
                queue_index += 2
            record["source_component"] = source
            binding["response_id"] = "response-duplex-media"
            binding["response_generation"] = 1
        elif segment == "speech.playout":
            record["source_component"] = "product.w2.browser.playout"
            binding["response_id"] = "response-duplex-media"
            binding["response_generation"] = 1
        elif segment == "speech.capture":
            record["source_component"] = "product.w2.media.capture"
    content = _v2_runtime_content(
        ("\n".join(json.dumps(item) for item in envelopes) + "\n").encode(),
        artifact_id="real-duplex-media",
        artifact_sequence=1,
        producer_id="gateway",
    )
    artifact = verify_w2_runtime_jsonl_content(
        artifact_id="real-duplex-media",
        sequence=1,
        content=content,
        **_runtime_trust_args(
            content,
            artifact_id="real-duplex-media",
            sequence=1,
            producer_id="gateway",
        ),
    )

    proven = _derive_v2_runtime_items((artifact,))
    assert W2LedgerItem.P1_AUDIO in proven
    assert W2LedgerItem.P2_MEDIA in proven


def test_v2_route_and_completion_must_share_exact_source_record() -> None:
    content = _v2_runtime_content(
        _runtime_content("mismatched-source", "speech.recognition"),
        artifact_id="mismatched-source",
        artifact_sequence=1,
        producer_id="gateway",
    )
    envelopes = [json.loads(line) for line in content.decode().splitlines()]
    completed = next(
        envelope["record"]
        for envelope in envelopes
        if envelope.get("record_kind") == "observation"
        and envelope["record"]["event_name"] == "segment.completed"
    )
    completed["source_record_id"] = "different-source-record"
    content = ("\n".join(json.dumps(item) for item in envelopes) + "\n").encode()

    with pytest.raises(W2GateContractViolation, match="no completed route"):
        verify_w2_runtime_jsonl_content(
            artifact_id="mismatched-source",
            sequence=1,
            content=content,
            **_runtime_trust_args(
                content,
                artifact_id="mismatched-source",
                sequence=1,
                producer_id="gateway",
            ),
        )


def test_v2_receipt_covers_all_runtime_digests_and_preserves_chain() -> None:
    runtime_digests = ["1" * 64, "2" * 64]
    content = _assisted_v2_content(
        artifact_id="showcase-receipt-1",
        sequence=10,
        receipt_type="human_observation",
        observed_content_sha256s=runtime_digests,
        observed_subject="showcase:1",
    )
    receipt = verify_w2_assisted_receipt_content(
        content,
        **_trust_args(
            W2EvidenceKind.HUMAN_OBSERVATION,
            content,
            artifact_id="showcase-receipt-1",
            sequence=10,
        ),
    )
    artifacts = {
        "gateway": SimpleNamespace(
            runtime_format_version=2,
            content_sha256=runtime_digests[0],
            evidence_set_id="evidence-set-1",
            evidence_kinds=frozenset({W2EvidenceKind.REAL_RUNTIME}),
            proven_subjects=frozenset(),
            receipt_evidence_set_id=None,
            attested_content_sha256=frozenset(),
        ),
        "agentserver": SimpleNamespace(
            runtime_format_version=2,
            content_sha256=runtime_digests[1],
            evidence_set_id="evidence-set-1",
            evidence_kinds=frozenset({W2EvidenceKind.REAL_RUNTIME}),
            proven_subjects=frozenset(),
            receipt_evidence_set_id=None,
            attested_content_sha256=frozenset(),
        ),
        receipt.artifact_id: receipt,
    }
    assert _has_v2_claim_attestation(
        ("gateway", "agentserver", receipt.artifact_id),
        artifacts,  # type: ignore[arg-type]
        subject="showcase:1",
        required_kind=W2EvidenceKind.HUMAN_OBSERVATION,
    )

    missing_content = _assisted_v2_content(
        artifact_id="showcase-receipt-missing",
        sequence=11,
        receipt_type="human_observation",
        observed_content_sha256s=runtime_digests[:1],
        observed_subject="showcase:1",
    )
    missing = verify_w2_assisted_receipt_content(
        missing_content,
        **_trust_args(
            W2EvidenceKind.HUMAN_OBSERVATION,
            missing_content,
            artifact_id="showcase-receipt-missing",
            sequence=11,
        ),
    )
    artifacts[missing.artifact_id] = missing
    assert not _has_v2_claim_attestation(
        ("gateway", "agentserver", missing.artifact_id),
        artifacts,  # type: ignore[arg-type]
        subject="showcase:1",
        required_kind=W2EvidenceKind.HUMAN_OBSERVATION,
    )

    wrong_set_content = _assisted_v2_content(
        artifact_id="showcase-receipt-wrong-set",
        sequence=12,
        receipt_type="human_observation",
        observed_content_sha256s=runtime_digests,
        observed_subject="showcase:1",
        evidence_set_id="different-evidence-set",
    )
    wrong_set = verify_w2_assisted_receipt_content(
        wrong_set_content,
        **_trust_args(
            W2EvidenceKind.HUMAN_OBSERVATION,
            wrong_set_content,
            artifact_id="showcase-receipt-wrong-set",
            sequence=12,
        ),
    )
    artifacts[wrong_set.artifact_id] = wrong_set
    assert not _has_v2_claim_attestation(
        ("gateway", "agentserver", wrong_set.artifact_id),
        artifacts,  # type: ignore[arg-type]
        subject="showcase:1",
        required_kind=W2EvidenceKind.HUMAN_OBSERVATION,
    )

    chained_content = _assisted_v2_content(
        artifact_id="showcase-receipt-2",
        sequence=13,
        receipt_type="human_observation",
        observed_content_sha256s=runtime_digests,
        observed_subject="showcase:2",
        previous_receipt_sha256=receipt.content_sha256,
    )
    chained = verify_w2_assisted_receipt_content(
        chained_content,
        **_trust_args(
            W2EvidenceKind.HUMAN_OBSERVATION,
            chained_content,
            artifact_id="showcase-receipt-2",
            sequence=13,
        ),
    )
    assert chained.receipt_predecessor_sha256 == receipt.content_sha256


def test_exact_assisted_subject_cannot_mint_a_ledger_claim() -> None:
    runtime_content = _runtime_content("audio-observed", "speech.capture")
    runtime = verify_w2_runtime_jsonl_content(
        artifact_id="audio-observed",
        sequence=1,
        content=runtime_content,
        **_trust_args(
            W2EvidenceKind.REAL_RUNTIME,
            runtime_content,
            artifact_id="audio-observed",
            sequence=1,
        ),
    )
    receipt_content = _assisted_content(
        "audio-witness",
        2,
        "human_observation",
        runtime.content_sha256,
        f"ledger:{W2LedgerItem.P1_AUDIO.value}",
    )
    receipt = verify_w2_assisted_receipt_content(
        receipt_content,
        **_trust_args(
            W2EvidenceKind.HUMAN_OBSERVATION,
            receipt_content,
            artifact_id="audio-witness",
            sequence=2,
        ),
    )

    assert receipt.proven_ledger_items == frozenset()
    assert receipt.proven_target_items == frozenset()


def test_atomic_runtime_mapping_does_not_overcredit_generic_completion() -> None:
    task_content = _runtime_content("ordinary-task-command", "task.command")
    task = verify_w2_runtime_jsonl_content(
        artifact_id="ordinary-task-command",
        sequence=1,
        content=task_content,
        **_trust_args(
            W2EvidenceKind.REAL_RUNTIME,
            task_content,
            artifact_id="ordinary-task-command",
            sequence=1,
        ),
    )
    capture_content = _runtime_content("ordinary-capture", "speech.capture")
    capture = verify_w2_runtime_jsonl_content(
        artifact_id="ordinary-capture",
        sequence=2,
        content=capture_content,
        **_trust_args(
            W2EvidenceKind.REAL_RUNTIME,
            capture_content,
            artifact_id="ordinary-capture",
            sequence=2,
        ),
    )

    assert task.proven_ledger_items == frozenset()
    assert not any(item.value.startswith("cross.") for item in task.proven_ledger_items)
    assert capture.proven_ledger_items == frozenset()


def test_exact_voice_task_bridge_runtime_proves_only_the_voice_bridge() -> None:
    content = _runtime_content(
        f"evidence-{W2LedgerItem.P3_VOICE_BRIDGE.value}", "task.command"
    )
    artifact = verify_w2_runtime_jsonl_content(
        artifact_id="voice-task-bridge",
        sequence=1,
        content=content,
        **_trust_args(
            W2EvidenceKind.REAL_RUNTIME,
            content,
            artifact_id="voice-task-bridge",
            sequence=1,
        ),
    )

    assert artifact.proven_ledger_items == frozenset({W2LedgerItem.P3_VOICE_BRIDGE})
    assert W2LedgerItem.P3_CORE not in artifact.proven_ledger_items
    assert W2LedgerItem.P3_UI not in artifact.proven_ledger_items


def test_dedicated_media_capture_alone_proves_no_media_item() -> None:
    content = _runtime_content("dedicated-media-capture", "speech.capture")
    artifact = verify_w2_runtime_jsonl_content(
        artifact_id="dedicated-media",
        sequence=1,
        content=content,
        **_trust_args(
            W2EvidenceKind.REAL_RUNTIME,
            content,
            artifact_id="dedicated-media",
            sequence=1,
        ),
    )

    assert artifact.proven_ledger_items == frozenset()


def test_ledger_score_is_derived_from_runtime_proof_not_caller_points() -> None:
    awards = list(_awards())
    original = awards[0]
    awards[0] = replace(original, points=1)

    result = _evaluate(awards=tuple(awards))

    assert result.section_scores[W2Section.P1] == 20
    assert result.total_score == 100
    assert result.status is W2GateStatus.FAIL
    assert (
        f"ledger item {original.item.value} points were not derived from evidence"
        in result.failures
    )


def test_total_score_cannot_hide_a_section_below_its_threshold() -> None:
    awards = list(_awards())
    awards[0] = W2LedgerAward(
        item=W2LedgerItem.P1_AUDIO,
        points=0,
        route_class=W2RouteClass.FORMAL,
        evidence_kinds=frozenset({W2EvidenceKind.AUTOMATED_CONFORMANCE}),
        evidence_ids=("p1-audio-zero",),
        target_route_owned=False,
    )

    result = _evaluate(awards=tuple(awards))

    assert result.total_score == 95
    assert result.status is W2GateStatus.FAIL
    assert "p1 score 15 is below 16" in result.failures


def test_gate1_is_independent_of_real_runtime_ledger_credit() -> None:
    result = _evaluate(verification=_verification(frontend_build_passed=False))

    assert result.status is W2GateStatus.FAIL
    assert (
        "Gate 1 verification/build/review/gap/flaky truth is incomplete"
        in result.failures
    )


def test_missing_or_failed_invariant_fails_closed() -> None:
    invariants = list(_invariants())
    invariants.pop()
    invariants[0] = W2InvariantEvidence(
        invariants[0].invariant, False, ("negative-invariant",)
    )

    result = _evaluate(invariants=tuple(invariants))

    assert result.status is W2GateStatus.FAIL
    assert "mandatory invariant evidence is incomplete" in result.failures
    assert "one or more mandatory invariants failed" in result.failures


def test_showcase_runs_must_share_all_candidate_bindings() -> None:
    runs = list(_runs())
    runs[2] = replace(runs[2], environment_id="environment-2")

    result = _evaluate(showcase_runs=tuple(runs))

    assert result.status is W2GateStatus.FAIL
    assert (
        "showcase runs do not share the candidate/environment/session/mode"
        in result.failures
    )


def test_showcase_runs_cannot_reuse_or_reorder_artifacts() -> None:
    runs = list(_runs())
    runs[1] = replace(runs[1], evidence_ids=runs[0].evidence_ids)
    reused = _evaluate(showcase_runs=tuple(runs))
    assert "showcase runs reused an evidence artifact" in reused.failures

    values: dict[str, object] = {
        "candidate": _candidate(),
        "verification": _verification(),
        "awards": _awards(),
        "invariants": _invariants(),
        "showcase_runs": _runs(),
        "journey_steps": _journey(),
        "faults": _faults(),
        "restart": _restart(),
    }
    artifacts = list(_artifacts(values))
    run_one_index = next(
        index
        for index, artifact in enumerate(artifacts)
        if artifact.artifact_id == "showcase-1-runtime"
    )
    run_three_index = next(
        index
        for index, artifact in enumerate(artifacts)
        if artifact.artifact_id == "showcase-3-runtime"
    )
    first = artifacts[run_one_index]
    third = artifacts[run_three_index]
    artifacts[run_one_index] = _reverify_artifact(first, sequence=third.sequence)
    artifacts[run_three_index] = _reverify_artifact(third, sequence=first.sequence)
    reordered = _evaluate(artifacts=tuple(artifacts))
    assert (
        "showcase artifacts are not three ordered consecutive runs"
        in reordered.failures
    )


def test_journey_steps_cannot_reuse_one_assisted_receipt() -> None:
    steps = list(_journey())
    first_receipt = steps[0].evidence_ids[1]
    steps[1] = replace(steps[1], evidence_ids=(steps[1].evidence_ids[0], first_receipt))

    result = _evaluate(journey_steps=tuple(steps))

    assert result.status is W2GateStatus.FAIL
    assert "Gate 2 journey steps reused an assisted receipt" in result.failures


def test_active_plane_requires_both_fault_classes_and_zero_false_effects() -> None:
    faults = list(_faults())
    faults[0] = replace(faults[0], non_retriable_observed=False)

    result = _evaluate(faults=tuple(faults))

    assert result.status is W2GateStatus.FAIL
    assert (
        "active plane p1.speech_media lacks complete fault evidence" in result.failures
    )


def test_fault_classes_require_independent_artifacts() -> None:
    with pytest.raises(W2GateContractViolation, match="distinct artifacts"):
        W2FaultEvidence(
            W2CapabilityPlane.P1_SPEECH_MEDIA,
            True,
            True,
            True,
            True,
            True,
            ("same-artifact",),
            ("same-artifact",),
            ("zero-effect",),
        )


def test_each_fault_class_requires_its_own_injected_artifact() -> None:
    values: dict[str, object] = {
        "candidate": _candidate(),
        "verification": _verification(),
        "awards": _awards(),
        "invariants": _invariants(),
        "showcase_runs": _runs(),
        "journey_steps": _journey(),
        "faults": _faults(),
        "restart": _restart(),
    }
    artifacts = list(_artifacts(values))
    target_id = _faults()[0].retriable_evidence_ids[1]
    index = next(
        index
        for index, artifact in enumerate(artifacts)
        if artifact.artifact_id == target_id
    )
    artifacts[index] = _reverify_artifact(
        artifacts[index],
        evidence_kinds=frozenset({W2EvidenceKind.AUTOMATED_CONFORMANCE}),
    )

    result = _evaluate(artifacts=tuple(artifacts))

    assert (
        "active plane p1.speech_media lacks injected-fault artifacts" in result.failures
    )


def test_fault_records_cannot_omit_a_declared_active_plane() -> None:
    result = _evaluate(faults=_faults()[1:])
    assert (
        "fault records do not cover exactly the active capability planes"
        in result.failures
    )


def test_scored_plane_cannot_be_omitted_from_the_active_set() -> None:
    active = frozenset(
        {
            W2CapabilityPlane.P2_CONVERSATION,
            W2CapabilityPlane.P3_TASK,
            W2CapabilityPlane.OBSERVABILITY,
        }
    )
    candidate = _candidate(active_planes=active)
    faults = tuple(evidence for evidence in _faults() if evidence.plane in active)
    result = _evaluate(candidate=candidate, faults=faults)
    assert "a scored capability plane was not declared active" in result.failures


def test_positive_credit_rejects_automated_only_or_unknown_routes() -> None:
    with pytest.raises(W2GateContractViolation, match="real runtime evidence"):
        W2LedgerAward(
            W2LedgerItem.P2_RUNTIME,
            1,
            W2RouteClass.FORMAL,
            frozenset({W2EvidenceKind.AUTOMATED_CONFORMANCE}),
            ("automated-only",),
            False,
        )
    with pytest.raises(W2GateContractViolation, match="cannot receive credit"):
        W2LedgerAward(
            W2LedgerItem.P2_RUNTIME,
            1,
            W2RouteClass.UNKNOWN,
            frozenset({W2EvidenceKind.REAL_RUNTIME}),
            ("unknown-route",),
            False,
        )


@pytest.mark.parametrize(
    "item",
    [
        W2LedgerItem.P3_CORE,
        W2LedgerItem.P3_EXECUTOR,
        W2LedgerItem.P3_VOICE_BRIDGE,
        W2LedgerItem.P3_PROGRESS,
        W2LedgerItem.P3_UI,
    ],
)
def test_d031_d057_forbid_even_partial_p3_substitute_credit(
    item: W2LedgerItem,
) -> None:
    with pytest.raises(W2GateContractViolation, match="D-031"):
        W2LedgerAward(
            item,
            1,
            W2RouteClass.DEMO_SUBSTITUTE,
            frozenset({W2EvidenceKind.REAL_RUNTIME}),
            ("legacy-substitute",),
            False,
        )


def test_artifact_kinds_cannot_be_self_declared_by_an_award() -> None:
    values: dict[str, object] = {
        "candidate": _candidate(),
        "verification": _verification(),
        "awards": _awards(),
        "invariants": _invariants(),
        "showcase_runs": _runs(),
        "journey_steps": _journey(),
        "faults": _faults(),
        "restart": _restart(),
    }
    artifacts = list(_artifacts(values))
    target_id = _awards()[0].evidence_ids[0]
    index = next(
        index
        for index, artifact in enumerate(artifacts)
        if artifact.artifact_id == target_id
    )
    artifacts[index] = _reverify_artifact(
        artifacts[index],
        evidence_kinds=frozenset({W2EvidenceKind.AUTOMATED_CONFORMANCE}),
    )
    result = _evaluate(artifacts=tuple(artifacts))
    assert "self-declared evidence kinds" in " ".join(result.failures)


def test_artifacts_are_bound_to_the_exact_candidate() -> None:
    values: dict[str, object] = {
        "candidate": _candidate(),
        "verification": _verification(),
        "awards": _awards(),
        "invariants": _invariants(),
        "showcase_runs": _runs(),
        "journey_steps": _journey(),
        "faults": _faults(),
        "restart": _restart(),
    }
    artifacts = list(_artifacts(values))
    artifacts[0] = _reverify_artifact(artifacts[0], environment_id="environment-other")
    result = _evaluate(artifacts=tuple(artifacts))
    assert (
        "an evidence artifact is not bound to this candidate record" in result.failures
    )


def test_unknown_evidence_artifact_is_rejected() -> None:
    with pytest.raises(W2GateContractViolation, match="unknown artifact"):
        _evaluate(artifacts=())


def test_sensitive_or_unbounded_labels_and_evidence_are_rejected() -> None:
    with pytest.raises(W2GateContractViolation, match="sensitive marker"):
        _candidate(network_label="api_key=do-not-record")
    with pytest.raises(W2GateContractViolation, match="sensitive marker"):
        _candidate(device_label="transcript:private")
    for bypass in (
        {"network_label": "authorization-bearer-private"},
        {"device_label": "transcript-private"},
        {"project_label": "api-key-sk-private"},
    ):
        with pytest.raises(W2GateContractViolation, match="sensitive marker"):
            _candidate(**bypass)
    with pytest.raises(W2GateContractViolation, match="at most"):
        _candidate(
            provider_labels=tuple(
                f"provider-{index}" for index in range(MAX_W2_PROVIDER_LABELS + 1)
            )
        )
    with pytest.raises(W2GateContractViolation, match="at most"):
        W2InvariantEvidence(
            W2Invariant.COMMITTED_ONLY,
            True,
            tuple(f"artifact-{index}" for index in range(MAX_W2_EVIDENCE_IDS + 1)),
        )


def test_gate_record_collections_have_a_hard_bound_before_iteration() -> None:
    with pytest.raises(W2GateContractViolation, match="bounded record limit"):
        _evaluate(
            artifacts=(
                _artifacts(
                    {
                        "candidate": _candidate(),
                        "verification": _verification(),
                        "awards": _awards(),
                        "invariants": _invariants(),
                        "showcase_runs": _runs(),
                        "journey_steps": _journey(),
                        "faults": _faults(),
                        "restart": _restart(),
                    }
                )[0],
            )
            * (MAX_W2_GATE_RECORDS + 1)
        )


def test_dirty_or_missing_gate0_truth_fails_even_with_full_arithmetic() -> None:
    result = _evaluate(
        candidate=_candidate(
            worktree_clean=False,
            isolated_runtime_data_observed=False,
            secrets_boundary_recorded=False,
            routes_and_flags_recorded=False,
            real_source_facts_observed=False,
            sanitized_route_trace_observed=False,
        )
    )
    assert result.status is W2GateStatus.FAIL
    assert "candidate worktree is not clean" in result.failures
    assert "isolated runtime data boundary was not observed" in result.failures
    assert "secrets boundary was not recorded" in result.failures
    assert "routes and flags were not recorded" in result.failures


def test_restart_must_reconcile_every_inflight_task_truthfully() -> None:
    result = _evaluate(
        restart=W2RestartEvidence(
            True,
            ("task-restart-1", "task-restart-2"),
            (
                W2TaskReconciliationEvidence(
                    "task-restart-1",
                    W2ReconciliationOutcome.TERMINAL,
                    ("restart-1",),
                ),
            ),
            ("restart-1",),
        )
    )
    assert (
        "restart reconciliation does not exactly cover in-flight tasks"
        in result.failures
    )


def test_duplicate_evidence_subjects_are_rejected() -> None:
    duplicate = (_awards()[0], _awards()[0])
    with pytest.raises(W2GateContractViolation, match="duplicate ledger item"):
        _evaluate(awards=duplicate)
