# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ScopeRef,
    TerminalOutcome,
)
from jiuwenswarm.server.live_voice.formal_task_models import (
    FormalAttemptState,
    PersistentAttemptRecord,
    PersistentTaskEvent,
)

from jiuwenswarm.server.live_voice.product_w2_observability import (
    W2_CANDIDATE_SHA_ENV,
    W2_ARTIFACT_ID_ENV,
    W2_ARTIFACT_SEQUENCE_ENV,
    W2_EVIDENCE_ENABLE_ENV,
    W2_EVIDENCE_PATH_ENV,
    W2_EVIDENCE_PRIVATE_KEY_PATH_ENV,
    W2_EVIDENCE_SIGNATURE_PATH_ENV,
    W2_EVIDENCE_SET_ID_ENV,
    W2_ENVIRONMENT_ID_ENV,
    W2_GATEWAY_EVIDENCE_PATH_ENV,
    W2_GATEWAY_EVIDENCE_PRIVATE_KEY_PATH_ENV,
    W2_GATEWAY_EVIDENCE_SIGNATURE_PATH_ENV,
    W2_GATEWAY_ARTIFACT_ID_ENV,
    W2_GATEWAY_ARTIFACT_SEQUENCE_ENV,
    W2_GATEWAY_PROCESS_EPOCH_ENV,
    W2_MODE_ID_ENV,
    W2_REPOSITORY_PATH_ENV,
    W2_PROCESS_EPOCH_ENV,
    W2_SESSION_ID_ENV,
    ProductW2ObservabilityOwner,
    create_gateway_w2_observability_owner_from_environment,
    create_product_w2_observability_owner_from_environment,
    product_result_execution_binding,
    product_result_agent_output_kind,
    product_result_has_terminal_d0_attempt,
    product_result_observation_ok,
    product_result_query_binding,
    product_result_task_id,
    product_result_task_event_facts,
    product_result_voice_task_bridge,
    product_result_voice_task_origin,
)
from jiuwenswarm.server.live_voice.project_code_executor import (
    DIRECT_PROJECT_EXECUTOR_REF_PREFIX,
    FORMAL_PROJECT_EXECUTOR_ID,
)
from jiuwenswarm.server.live_voice.w2_evidence_exporter import (
    W2EvidenceExporterError,
    W2JsonlEvidenceExporter,
)
from jiuwenswarm.server.live_voice.w2_demo_gate import (
    w2_artifact_signature_payload,
)


def _enable(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    agent_private = path.parent / "agentserver-evidence.private"
    gateway_private = path.parent / "gateway-evidence.private"
    agent_private.write_text("11" * 32 + "\n", encoding="ascii")
    gateway_private.write_text("22" * 32 + "\n", encoding="ascii")
    monkeypatch.setenv(W2_EVIDENCE_ENABLE_ENV, "1")
    monkeypatch.setenv(W2_EVIDENCE_PATH_ENV, str(path.resolve()))
    monkeypatch.setenv(W2_EVIDENCE_PRIVATE_KEY_PATH_ENV, str(agent_private.resolve()))
    monkeypatch.setenv(
        W2_EVIDENCE_SIGNATURE_PATH_ENV,
        str((path.parent / "agentserver-evidence.sig").resolve()),
    )
    monkeypatch.setenv(
        W2_GATEWAY_EVIDENCE_PRIVATE_KEY_PATH_ENV,
        str(gateway_private.resolve()),
    )
    monkeypatch.setenv(
        W2_GATEWAY_EVIDENCE_SIGNATURE_PATH_ENV,
        str((path.parent / "gateway-evidence.sig").resolve()),
    )
    monkeypatch.setenv(W2_CANDIDATE_SHA_ENV, "a" * 40)
    monkeypatch.setenv(W2_ENVIRONMENT_ID_ENV, "environment-w2")
    monkeypatch.setenv(W2_SESSION_ID_ENV, "session-w2")
    monkeypatch.setenv(W2_MODE_ID_ENV, "integrated-formal")
    monkeypatch.setenv(W2_REPOSITORY_PATH_ENV, str(path.parent.resolve()))
    monkeypatch.setenv(W2_EVIDENCE_SET_ID_ENV, "evidence-set-w2")
    monkeypatch.setenv(W2_ARTIFACT_ID_ENV, "agentserver-artifact-1")
    monkeypatch.setenv(W2_ARTIFACT_SEQUENCE_ENV, "1")
    monkeypatch.setenv(W2_PROCESS_EPOCH_ENV, "agentserver-epoch-1")
    monkeypatch.setenv(W2_GATEWAY_ARTIFACT_ID_ENV, "gateway-artifact-1")
    monkeypatch.setenv(W2_GATEWAY_ARTIFACT_SEQUENCE_ENV, "2")
    monkeypatch.setenv(W2_GATEWAY_PROCESS_EPOCH_ENV, "gateway-epoch-1")
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_w2_observability."
        "verify_w2_candidate_checkout",
        lambda **_kwargs: "a" * 40,
    )


def _observation_envelopes(path: Path) -> list[dict[str, object]]:
    return [
        record
        for record in (
            json.loads(line) for line in path.read_text("utf-8").splitlines()
        )
        if record["record_kind"] == "observation"
    ]


def test_feature_off_does_not_inspect_an_invalid_evidence_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(W2_EVIDENCE_ENABLE_ENV, raising=False)
    monkeypatch.setenv(W2_EVIDENCE_PATH_ENV, "not-an-absolute-path")

    assert create_product_w2_observability_owner_from_environment() is None


def test_query_evidence_prefers_server_owned_task_correlation() -> None:
    def event(
        *, event_id: str, seq: int, attempt_id: str = "attempt-1", correlation_id: str
    ) -> dict[str, object]:
        terminal = seq == 2
        return {
            "event_id": event_id,
            "task_id": "task-1",
            "attempt_id": attempt_id,
            "seq": seq,
            "state": "terminal" if terminal else "running",
            "outcome": "completed" if terminal else None,
            "correlation_id": correlation_id,
            "occurred_at": f"2026-08-09T16:0{seq}:00Z",
        }

    task_payload = {
        "result": {
            "task": {
                "task_id": "task-1",
                "attempt_id": "attempt-1",
                "correlation_id": "correlation-task",
            },
            "attempt": {"task_id": "task-1", "attempt_id": "attempt-1"},
        }
    }
    events_payload = {
        "result": {
            "task_id": "task-1",
            "events": [
                event(
                    event_id="event-1",
                    seq=1,
                    correlation_id="correlation-task",
                ),
                event(
                    event_id="event-2",
                    seq=2,
                    correlation_id="correlation-task",
                ),
            ]
        }
    }
    conflicting = {
        "result": {
            "task_id": "task-1",
            "events": [
                event(
                    event_id="event-conflict-1",
                    seq=1,
                    correlation_id="correlation-task",
                ),
                event(
                    event_id="event-conflict-2",
                    seq=2,
                    correlation_id="correlation-other",
                ),
            ]
        }
    }

    assert (
        product_result_query_binding(
            "task.status", task_payload, request_id="transport-status-1"
        )
        == ("correlation-task", "task-1", "attempt-1")
    )
    assert (
        product_result_query_binding(
            "task.events", events_payload, request_id="transport-events-1"
        )
        == ("correlation-task", "task-1", "attempt-1")
    )
    assert (
        product_result_query_binding(
            "task.list",
            {
                "result": {
                    "tasks": [
                        {
                            "task_id": "task-list-1",
                            "attempt_id": "attempt-list-1",
                            "correlation_id": "correlation-task",
                        }
                    ]
                }
            },
            request_id="transport-list-1",
        )
        == ("correlation-task", "task-list-1", "attempt-list-1")
    )
    assert (
        product_result_query_binding(
            "task.events",
            {
                "result": {
                    "task_id": "task-1",
                    "events": [
                        {
                            "task_id": "task-1",
                            "attempt_id": "attempt-1",
                            "correlation_id": "correlation-task",
                        }
                    ],
                }
            },
            request_id="transport-malformed-event",
        )
        is None
    )
    for unsafe_event in (
        event(
            event_id="event-non-utc",
            seq=1,
            correlation_id="correlation-task",
        )
        | {"occurred_at": "2026-08-09T17:00:00+01:00"},
        event(
            event_id="event-unsafe-seq",
            seq=9_007_199_254_740_992,
            correlation_id="correlation-task",
        ),
        event(
            event_id="event-sensitive",
            seq=1,
            correlation_id="bearer-secret",
        ),
    ):
        assert (
            product_result_query_binding(
                "task.events",
                {"result": {"task_id": "task-1", "events": [unsafe_event]}},
                request_id="transport-unsafe-event",
            )
            is None
        )
    assert (
        product_result_query_binding(
            "task.events", conflicting, request_id="transport-conflict"
        )
        is None
    )
    assert (
        product_result_query_binding(
            "task.events",
            {
                "result": {
                    "task_id": "task-1",
                    "events": [
                        event(
                            event_id="event-attempt-1",
                            seq=1,
                            correlation_id="correlation-task",
                        ),
                        event(
                            event_id="event-attempt-2",
                            seq=2,
                            attempt_id="attempt-2",
                            correlation_id="correlation-task",
                        ),
                    ]
                }
            },
            request_id="transport-multiple-attempts",
        )
        is None
    )
    assert (
        product_result_query_binding(
            "task.events",
            {"result": {"task_id": "task-1", "events": []}},
            request_id="correlation-task",
        )
        is None
    )
    assert (
        product_result_query_binding(
            "task.status",
            {"result": {"task": {"correlation_id": ""}}},
            request_id="transport-malformed",
        )
        is None
    )

    with pytest.raises(ValueError, match="request_id"):
        product_result_query_binding("task.status", task_payload, request_id="")

@pytest.mark.asyncio
async def test_incremental_task_queries_keep_one_correlation_and_unique_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "w2-incremental-task-events.jsonl"
    _enable(monkeypatch, path)
    owner = create_product_w2_observability_owner_from_environment()
    assert owner is not None
    invalid_event = {
        "event_id": "task-invalid-1",
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "seq": 0,
        "state": "not-a-task-state",
        "outcome": None,
        "correlation_id": "correlation-poison",
        "occurred_at": "2026-08-09T15:59:00Z",
    }
    assert not await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-poison",
        request_id="transport-events-invalid",
        operation="task.events",
        result_ok=True,
        task_id="task-1",
        attempt_id="attempt-1",
        task_event_facts=(invalid_event,),
    )
    list_payload = {
        "result": {
            "tasks": [
                {
                    "task_id": "task-1",
                    "attempt_id": "attempt-1",
                    "correlation_id": "correlation-task",
                }
            ]
        }
    }
    list_binding = product_result_query_binding(
        "task.list", list_payload, request_id="transport-list"
    )
    assert list_binding == ("correlation-task", "task-1", "attempt-1")
    list_correlation_id, list_task_id, list_attempt_id = list_binding
    assert await owner.observe_route(
        session_id="session-w2",
        correlation_id=list_correlation_id,
        request_id="transport-list",
        operation="task.list",
        result_ok=True,
        task_id=list_task_id,
        attempt_id=list_attempt_id,
    )
    running_payload = {
        "result": {
            "task_id": "task-1",
            "events": [
                {
                    "event_id": "task-running-1",
                    "task_id": "task-1",
                    "attempt_id": "attempt-1",
                    "seq": 1,
                    "state": "running",
                    "outcome": None,
                    "correlation_id": "correlation-task",
                    "occurred_at": "2026-08-09T16:00:00Z",
                }
            ],
        }
    }
    terminal_payload = {
        "result": {
            "task_id": "task-1",
            "events": [
                {
                    "event_id": "task-terminal-1",
                    "task_id": "task-1",
                    "attempt_id": "attempt-1",
                    "seq": 2,
                    "state": "terminal",
                    "outcome": "completed",
                    "correlation_id": "correlation-task",
                    "occurred_at": "2026-08-09T16:01:00Z",
                }
            ],
        }
    }
    for request_id, payload in (
        ("transport-events-running", running_payload),
        ("transport-events-terminal", terminal_payload),
    ):
        facts = product_result_task_event_facts(payload)
        binding = product_result_query_binding(
            "task.events", payload, request_id=request_id
        )
        assert binding == ("correlation-task", "task-1", "attempt-1")
        assert await owner.observe_route(
            session_id="session-w2",
            correlation_id=binding[0],
            request_id=request_id,
            operation="task.events",
            result_ok=True,
            task_id=binding[1],
            attempt_id=binding[2],
            task_event_facts=facts,
        )
    await owner.close()

    observations = [entry["record"] for entry in _observation_envelopes(path)]
    list_completion = next(
        item
        for item in observations
        if item["source_component"] == "product.w2.task.list"
        and item["event_name"] == "segment.completed"
    )
    assert list_completion["binding"]["task_id"] == "task-1"
    assert list_completion["binding"]["attempt_id"] == "attempt-1"
    event_sources = [
        item["source_record_id"]
        for item in observations
        if item["source_component"] == "product.w2.task.events"
        and item["event_name"] == "segment.completed"
    ]
    assert len(event_sources) == len(set(event_sources)) == 2
    states = [
        item
        for item in observations
        if item["source_component"] == "product.w2.task.event"
    ]
    assert [(item["source_seq"], item["state"]) for item in states] == [
        (1, "running"),
        (2, "terminal"),
    ]
    terminal_state_index = next(
        index
        for index, item in enumerate(observations)
        if item["source_component"] == "product.w2.task.event"
        and item["state"] == "terminal"
    )
    terminal_query_index = next(
        index
        for index, item in enumerate(observations)
        if item["source_component"] == "product.w2.task.events"
        and item["event_name"] == "segment.completed"
        and item["source_record_id"] != event_sources[0]
    )
    assert terminal_state_index < terminal_query_index


@pytest.mark.asyncio
async def test_product_owner_emits_one_exact_sanitized_route_and_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "w2-product.jsonl"
    _enable(monkeypatch, path)
    owner = create_product_w2_observability_owner_from_environment()
    assert type(owner) is ProductW2ObservabilityOwner

    accepted = await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-w2",
        request_id="request-w2",
        operation="live_voice.composition.p2.submit",
        result_ok=True,
        interaction_id="interaction-w2",
        turn_id="turn-w2",
        round_id="round-w2",
    )
    assert not await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-w2",
        request_id="wrong-producer-speech",
        operation="speech.recognize.batch",
        result_ok=True,
        interaction_id="interaction-w2",
    )
    await owner.close()

    signature = path.parent / "agentserver-evidence.sig"
    Ed25519PrivateKey.from_private_bytes(bytes.fromhex("11" * 32)).public_key().verify(
        bytes.fromhex(signature.read_text(encoding="ascii").strip()),
        w2_artifact_signature_payload(
            kind="runtime_jsonl",
            artifact_id="agentserver-artifact-1",
            sequence=1,
            source_label=None,
            content=path.read_bytes(),
        ),
    )

    assert accepted is True
    records = _observation_envelopes(path)
    assert len(records) == 4
    record = records[0]["record"]
    assert record["binding"] == {
        "correlation_id": "correlation-w2",
        "interaction_id": "interaction-w2",
        "turn_id": "turn-w2",
        "response_id": None,
        "response_generation": None,
        "round_id": "round-w2",
        "task_id": None,
        "attempt_id": None,
    }
    assert record["event_name"] == "route.selected"
    assert [entry["record"]["segment_name"] for entry in records] == [
        "runtime.turn",
        "runtime.turn",
        "agent.dispatch",
        "agent.dispatch",
    ]
    assert records[1]["record"]["event_name"] == "segment.completed"
    assert records[2]["record"]["binding"]["round_id"] == "round-w2"
    assert all(
        entry["record"]["source_component"] == "product.w2.p2.submit.agent"
        for entry in records
    )
    assert records[0]["candidate"]["session_id"] == "session-w2"
    assert "request-w2" not in path.read_text("utf-8")


@pytest.mark.asyncio
async def test_p2_retriable_presentation_fault_preserves_exact_product_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "w2-p2-retriable-fault.jsonl"
    _enable(monkeypatch, path)
    owner = create_product_w2_observability_owner_from_environment()
    assert owner is not None
    assert await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-w2",
        request_id="request-p2-active",
        operation="live_voice.composition.p2.activate",
        result_ok=True,
        interaction_id="interaction-w2",
    )

    assert await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-w2",
        request_id="request-p2-retriable-presentation-fault",
        operation="live_voice.composition.p2.presentation.ack",
        result_ok=False,
        interaction_id="interaction-w2",
        response_id="response-w2",
        response_generation=7,
        error_code="UNAVAILABLE",
    )
    await owner.close()

    records = [entry["record"] for entry in _observation_envelopes(path)]
    fault_records = [
        record for record in records if record["event_name"] == "segment.failed"
    ]
    assert len(fault_records) == 1
    assert fault_records[0]["segment_name"] == "runtime.presentation"
    assert fault_records[0]["source_component"] == "product.w2.p2.presentation"
    assert fault_records[0]["error_code"] == "UNAVAILABLE"
    assert fault_records[0]["reason_code"] == "UNAVAILABLE"
    assert fault_records[0]["binding"] == {
        "correlation_id": "correlation-w2",
        "interaction_id": "interaction-w2",
        "turn_id": None,
        "response_id": "response-w2",
        "response_generation": 7,
        "round_id": None,
        "task_id": None,
        "attempt_id": None,
    }
    assert all(
        record["source_record_id"] != fault_records[0]["source_record_id"]
        for record in records
        if record["event_name"] == "segment.completed"
    )


@pytest.mark.asyncio
async def test_p3_stale_retry_fault_has_no_matching_completed_product_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "w2-p3-stale-fault.jsonl"
    _enable(monkeypatch, path)
    owner = create_product_w2_observability_owner_from_environment()
    assert owner is not None
    assert await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-w2",
        request_id="request-task-create",
        operation="live_voice.composition.p3.mutate",
        result_ok=True,
        task_id="task-1",
        attempt_id="attempt-1",
        task_operation="task.create",
    )
    assert await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-w2",
        request_id="request-task-retry-stale",
        operation="live_voice.composition.p3.mutate",
        result_ok=False,
        task_id="task-1",
        task_operation="task.retry",
        error_code="STALE",
    )
    await owner.close()

    records = [entry["record"] for entry in _observation_envelopes(path)]
    fault_records = [
        record for record in records if record["event_name"] == "segment.failed"
    ]
    assert len(fault_records) == 1
    fault = fault_records[0]
    assert fault["segment_name"] == "task.command"
    assert fault["source_component"] == "product.w2.task.retry"
    assert fault["error_code"] == "STALE"
    assert fault["binding"]["task_id"] == "task-1"
    assert all(
        record["source_component"] != fault["source_component"]
        for record in records
        if record["event_name"] == "segment.completed"
    )


@pytest.mark.asyncio
async def test_mismatched_route_is_rejected_and_export_failure_never_changes_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "w2-product.jsonl"
    _enable(monkeypatch, path)
    owner = create_product_w2_observability_owner_from_environment()
    assert owner is not None
    assert await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-w2",
        request_id="request-1",
        operation="live_voice.composition.p2.submit",
        result_ok=True,
        interaction_id="interaction-1",
        turn_id="turn-1",
        round_id="round-1",
    )

    assert not await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-other",
        request_id="request-2",
        operation="live_voice.composition.p2.submit",
        result_ok=True,
        interaction_id="interaction-2",
        turn_id="turn-2",
        round_id="round-2",
    )
    business_result = {"ok": True, "result": "unchanged"}

    def fail_append(self: W2JsonlEvidenceExporter, *_args: object) -> bool:
        del self
        raise W2EvidenceExporterError("injected sink failure")

    monkeypatch.setattr(W2JsonlEvidenceExporter, "_append", fail_append)
    # Enqueue acceptance remains diagnostic-only even if the async sink later
    # fails; settling/close must not mutate the already-owned business result.
    await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-w2",
        request_id="request-3",
        operation="live_voice.composition.p2.submit",
        result_ok=True,
        interaction_id="interaction-3",
        turn_id="turn-3",
        round_id="round-3",
    )
    await owner.close()
    assert business_result == {"ok": True, "result": "unchanged"}


@pytest.mark.asyncio
async def test_denied_request_cannot_mint_route_or_poison_later_valid_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "w2-product.jsonl"
    _enable(monkeypatch, path)
    owner = create_product_w2_observability_owner_from_environment()
    assert owner is not None

    assert not await owner.observe_route(
        session_id="session-w2",
        correlation_id="denied-correlation",
        request_id="denied-request",
        operation="live_voice.composition.p2.submit",
        result_ok=False,
        error_code="PERMISSION_DENIED",
    )
    assert not path.exists()
    assert await owner.observe_route(
        session_id="session-w2",
        correlation_id="valid-correlation",
        request_id="valid-request",
        operation="live_voice.composition.p3.mutate",
        result_ok=True,
        task_id="task-1",
        attempt_id="attempt-1",
        task_operation="task.create",
    )
    await owner.close()

    records = _observation_envelopes(path)
    assert [entry["record"]["event_name"] for entry in records] == [
        "route.selected",
        "segment.completed",
    ]
    assert all(
        entry["record"]["binding"]["correlation_id"] == "valid-correlation"
        for entry in records
    )
    assert all(entry["record"]["binding"]["task_id"] == "task-1" for entry in records)


@pytest.mark.asyncio
async def test_gateway_owner_records_exact_p1_media_recognition_and_synthesis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    product_path = tmp_path / "unused-product.jsonl"
    gateway_path = tmp_path / "w2-gateway.jsonl"
    _enable(monkeypatch, product_path)
    monkeypatch.setenv(W2_GATEWAY_EVIDENCE_PATH_ENV, str(gateway_path.resolve()))
    owner = create_gateway_w2_observability_owner_from_environment()
    assert owner is not None

    assert await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-w2",
        request_id="capture-request",
        operation="media.capture",
        result_ok=True,
        interaction_id="interaction-1",
    )
    assert await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-w2",
        request_id="recognition-request",
        operation="speech.recognize.batch",
        result_ok=True,
        interaction_id="interaction-1",
    )
    assert await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-w2",
        request_id="synthesis-request",
        operation="speech.synthesize.batch",
        result_ok=True,
        interaction_id="interaction-1",
        response_id="response-1",
        response_generation=1,
    )
    assert await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-w2",
        request_id="recognition-timeout",
        operation="speech.recognize.batch",
        result_ok=False,
        error_code="TIMEOUT",
        interaction_id="interaction-2",
    )
    assert await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-w2",
        request_id="playout-receipt-1",
        operation="media.playout.receipt",
        result_ok=True,
        interaction_id="interaction-1",
        response_id="response-1",
        response_generation=1,
    )
    assert not await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-w2",
        request_id="wrong-producer-task",
        operation="task.list",
        result_ok=True,
    )
    await owner.close()

    records = _observation_envelopes(gateway_path)
    assert [entry["record"]["segment_name"] for entry in records] == [
        "speech.capture",
        "speech.capture",
        "speech.recognition",
        "speech.recognition",
        "speech.synthesis",
        "speech.synthesis",
        "speech.recognition",
        "speech.playout",
        "speech.playout",
    ]
    assert [entry["record"]["event_name"] for entry in records] == [
        "route.selected",
        "segment.completed",
        "route.selected",
        "segment.completed",
        "route.selected",
        "segment.completed",
        "segment.failed",
        "route.selected",
        "segment.completed",
    ]
    assert records[-3]["record"]["source_component"] == ("product.w2.speech.recognize")
    assert [entry["record"]["source_component"] for entry in records[-2:]] == [
        "product.w2.browser.playout",
        "product.w2.browser.playout",
    ]
    assert all(entry["candidate"]["session_id"] == "session-w2" for entry in records)


@pytest.mark.asyncio
async def test_terminal_direct_status_emits_exact_executor_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "w2-product.jsonl"
    _enable(monkeypatch, path)
    owner = create_product_w2_observability_owner_from_environment()
    assert owner is not None
    payload = {
        "result": {
            "task": {"task_id": "task-1", "attempt_id": "attempt-1"},
            "attempt": {
                "attempt_id": "attempt-1",
                "task_id": "task-1",
                "executor_id": FORMAL_PROJECT_EXECUTOR_ID,
                "executor_ref": f"{DIRECT_PROJECT_EXECUTOR_REF_PREFIX}attempt-1",
                "state": "terminal",
                "outcome": "completed",
                "source_seq": 2,
            },
        }
    }
    task_id, attempt_id = product_result_task_id({}, payload)

    assert product_result_has_terminal_d0_attempt(payload)
    assert await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-w2",
        request_id="status-request",
        operation="task.status",
        result_ok=True,
        task_id=task_id,
        attempt_id=attempt_id,
        terminal_d0_attempt=True,
    )
    await owner.close()

    records = _observation_envelopes(path)
    assert [entry["record"]["segment_name"] for entry in records] == [
        "task.progress",
        "task.progress",
        "task.attempt",
        "task.attempt",
    ]
    assert records[-1]["record"]["binding"]["attempt_id"] == "attempt-1"


@pytest.mark.asyncio
async def test_reconciliation_observation_requires_typed_durable_direct_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "w2-reconciliation.jsonl"
    _enable(monkeypatch, path)
    owner = create_product_w2_observability_owner_from_environment()
    assert owner is not None
    attempt = PersistentAttemptRecord(
        attempt_id="attempt-restart-1",
        task_id="task-restart-1",
        executor_id=FORMAL_PROJECT_EXECUTOR_ID,
        executor_ref=f"{DIRECT_PROJECT_EXECUTOR_REF_PREFIX}attempt-restart-1",
        state=FormalAttemptState.TERMINAL,
        outcome=TerminalOutcome.INTERRUPTED,
        source_seq=1,
    )
    event = PersistentTaskEvent(
        event_id="event-restart-terminal-1",
        task_id=attempt.task_id,
        attempt_id=attempt.attempt_id,
        scope=ScopeRef("user-1", "project-1", "session-w2", Assurance.AUTHENTICATED),
        seq=4,
        event_type="task.terminal",
        state="terminal",
        outcome="interrupted",
        producer="task_core.reconciliation",
        source_event_id=None,
        causation_id="reconciliation:attempt-restart-1",
        correlation_id="correlation-w2",
        occurred_at="2026-08-08T00:00:00Z",
        details={"reason": "EXECUTOR_ATTEMPT_LOST"},
    )

    assert await owner.observe_reconciliation_event(event, attempt)
    assert not await owner.observe_reconciliation_event(event.to_dict(), attempt)
    assert not await owner.observe_reconciliation_event(
        replace(
            event,
            scope=ScopeRef(
                "user-1", "project-1", "session-other", Assurance.AUTHENTICATED
            ),
        ),
        attempt,
    )
    await owner.close()

    records = _observation_envelopes(path)
    assert len(records) == 1
    record = records[0]["record"]
    assert record["source_component"] == "product.w2.task.reconciliation"
    assert record["segment_name"] == "task.progress"
    assert record["event_name"] == "task.state_observed"
    assert record["binding"]["task_id"] == attempt.task_id
    assert record["binding"]["attempt_id"] == attempt.attempt_id
    assert record["source_seq"] == event.seq
    assert record["outcome"] == "interrupted"


def test_d0_executor_proof_rejects_nonterminal_or_legacy_attempts() -> None:
    base = {
        "attempt_id": "attempt-1",
        "task_id": "task-1",
        "executor_id": FORMAL_PROJECT_EXECUTOR_ID,
        "executor_ref": f"{DIRECT_PROJECT_EXECUTOR_REF_PREFIX}attempt-1",
        "state": "terminal",
        "outcome": "completed",
        "source_seq": 2,
    }
    for updates in (
        {"state": "running", "outcome": None},
        {"outcome": "failed"},
        {"outcome": "cancelled"},
        {"executor_ref": "legacy:attempt-1"},
        {"executor_id": "legacy"},
        {"source_seq": True},
    ):
        assert not product_result_has_terminal_d0_attempt(
            {"result": {"attempt": {**base, **updates}}}
        )


def test_p2_observation_requires_exact_semantic_result_and_real_ids() -> None:
    params = {"turn_id": "turn-1"}
    payload = {
        "result": {
            "status": "round_accepted",
            "round_id": "round-1",
            "response": {
                "interaction_id": "interaction-1",
                "response_id": "response-1",
                "response_generation": 0,
            },
        }
    }

    assert product_result_execution_binding(params, payload) == (
        "turn-1",
        "round-1",
    )
    assert product_result_observation_ok(
        "live_voice.composition.p2.submit", result_ok=True, payload=payload
    )
    assert not product_result_observation_ok(
        "live_voice.composition.p2.submit",
        result_ok=True,
        payload={"result": {"status": "round_accepted"}},
    )
    for event_type, expected in (
        ("chat.tool_call", "tool_call"),
        ("chat.tool_result", "tool_result"),
        ("chat.final", "final"),
    ):
        assert (
            product_result_agent_output_kind(
                {
                    "result": {
                        "status": "notification",
                        "agent_event": {"event_type": event_type},
                        "presentation_unit": (
                            {"unit_id": "final-1"}
                            if event_type == "chat.final"
                            else None
                        ),
                    }
                }
            )
            == expected
        )
    assert product_result_voice_task_origin(
        {
            "result": {
                "status": "task_origin_accepted",
                "turn_id": "turn-voice-1",
                "commit_id": "commit-voice-1",
            }
        }
    )
    assert not product_result_voice_task_origin(payload)
    assert not product_result_observation_ok(
        "live_voice.composition.p2.presentation.ack",
        result_ok=True,
        payload={
            "result": {
                "status": "presentation_acknowledged",
                "accepted": False,
            }
        },
    )


@pytest.mark.asyncio
async def test_task_events_emit_exact_authority_sequence_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "w2-task-events.jsonl"
    _enable(monkeypatch, path)
    owner = create_product_w2_observability_owner_from_environment()
    assert owner is not None
    payload = {
        "result": {
            "task_id": "task-1",
            "events": [
                {
                    "event_id": "task-event-1",
                    "task_id": "task-1",
                    "attempt_id": "attempt-1",
                    "seq": 1,
                    "state": "running",
                    "outcome": None,
                    "correlation_id": "correlation-task",
                    "occurred_at": "2026-08-07T16:00:00Z",
                }
            ],
        }
    }
    facts = product_result_task_event_facts(payload)
    assert len(facts) == 1
    assert not await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-foreign",
        request_id="task-events-wrong-attempt",
        operation="task.events",
        result_ok=True,
        task_id="task-1",
        attempt_id="attempt-foreign",
        task_event_facts=facts,
    )
    assert await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-task",
        request_id="task-events-request",
        operation="task.events",
        result_ok=True,
        task_id="task-1",
        attempt_id="attempt-1",
        task_event_facts=facts,
    )
    await owner.close()

    observations = [entry["record"] for entry in _observation_envelopes(path)]
    state = [
        item for item in observations if item["event_name"] == "task.state_observed"
    ]
    assert len(state) == 1
    assert state[0]["source_event_id"] == "task-event-1"
    assert state[0]["source_seq"] == 1
    assert state[0]["binding"]["attempt_id"] == "attempt-1"


@pytest.mark.asyncio
async def test_terminal_task_context_is_not_injected_into_later_conversation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "w2-terminal-task-context.jsonl"
    _enable(monkeypatch, path)
    owner = create_product_w2_observability_owner_from_environment()
    assert owner is not None
    assert await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-task",
        request_id="task-create",
        operation="live_voice.composition.p3.mutate",
        result_ok=True,
        task_id="task-1",
        attempt_id="attempt-1",
        task_operation="task.create",
    )
    terminal = (
        {
            "event_id": "task-terminal-1",
            "task_id": "task-1",
            "attempt_id": "attempt-1",
            "seq": 2,
            "state": "terminal",
            "outcome": "completed",
            "correlation_id": "correlation-task",
            "occurred_at": "2026-08-07T16:01:00Z",
        },
    )
    assert await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-task",
        request_id="task-events-terminal",
        operation="task.events",
        result_ok=True,
        task_id="task-1",
        attempt_id="attempt-1",
        task_event_facts=terminal,
    )
    assert await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-task",
        request_id="later-conversation",
        operation="live_voice.composition.p2.notification.next",
        result_ok=True,
        round_id="round-after-terminal",
    )
    await owner.close()

    later = [
        entry["record"]
        for entry in _observation_envelopes(path)
        if entry["record"]["source_record_id"]
        == "w2-request-" + hashlib.sha256(b"later-conversation").hexdigest()[:32]
    ]
    assert later
    assert all(item["binding"]["task_id"] is None for item in later)


@pytest.mark.asyncio
async def test_voice_task_bridge_is_exact_success_and_has_distinct_runtime_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "w2-voice-task.jsonl"
    _enable(monkeypatch, path)
    owner = create_product_w2_observability_owner_from_environment()
    assert owner is not None
    params = {
        "operation": "task.create",
        "source": "voice",
        "turn_id": "turn-voice-1",
        "commit_id": "commit-voice-1",
    }
    payload = {
        "result": {
            "status": "mutation_processed",
            "operation": "task.create",
            "formal_task_result": {"task_id": "task-voice-1"},
        }
    }
    assert product_result_voice_task_bridge(params, payload)
    assert not product_result_voice_task_bridge(
        {**params, "source": "structured"}, payload
    )
    assert not product_result_voice_task_bridge(
        params, {"result": {**payload["result"], "formal_task_result": None}}
    )
    assert await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-voice-task",
        request_id="request-voice-task",
        operation="live_voice.composition.p3.mutate",
        result_ok=True,
        task_id="task-voice-1",
        voice_task_bridge=True,
        task_operation="task.create",
    )
    await owner.close()

    records = _observation_envelopes(path)
    assert [entry["record"]["segment_name"] for entry in records] == [
        "task.command",
        "task.command",
        "task.command",
        "task.command",
    ]
    assert [entry["record"]["source_component"] for entry in records] == [
        "product.w2.task.create",
        "product.w2.task.create",
        "product.voice_task_bridge",
        "product.voice_task_bridge",
    ]


@pytest.mark.asyncio
async def test_origin_barge_and_ui_progress_emit_only_exact_product_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "w2-exact-facts.jsonl"
    _enable(monkeypatch, path)
    owner = create_product_w2_observability_owner_from_environment()
    assert owner is not None

    assert await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-exact",
        request_id="origin-request",
        operation="live_voice.composition.p2.submit",
        result_ok=True,
        interaction_id="interaction-exact",
        turn_id="turn-exact",
        voice_task_origin=True,
    )
    assert await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-exact",
        request_id="barge-request",
        operation="live_voice.composition.p2.barge_in",
        result_ok=True,
        interaction_id="interaction-exact",
        response_id="response-exact",
        response_generation=1,
    )
    assert await owner.observe_route(
        session_id="session-w2",
        correlation_id="correlation-exact",
        request_id="progress-request",
        operation="live_voice.composition.p3.progress.ack",
        result_ok=True,
        task_id="task-exact",
    )
    await owner.close()

    records = [entry["record"] for entry in _observation_envelopes(path)]
    assert [record["source_component"] for record in records] == [
        "product.voice_task_origin",
        "product.voice_task_origin",
        "product.w2.p2.barge",
        "product.w2.p3.progress",
        "product.w2.p3.progress",
        "product.w2.p3.ui",
        "product.w2.p3.ui",
    ]
    assert records[2]["event_name"] == "cancel.acknowledged"
    assert records[2]["cancel_scope"] == "playback.stop"
