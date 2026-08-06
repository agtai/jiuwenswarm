# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Mapping
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
from jiuwenswarm.server.live_voice.formal_task_models import (
    FormalTaskState,
    OutboxKind,
    OutboxState,
    PersistentOutboxItem,
    PersistentTaskEvent,
    PersistentTaskRecord,
)
from jiuwenswarm.server.live_voice.observability import (
    CANCEL_SCOPES,
    CANCEL_TARGET_SEGMENT_MATRIX,
    ERROR_CODES,
    EVENT_SEMANTIC_MATRIX,
    EVENT_NAMES,
    FAILURE_ERROR_MATRIX,
    FAILURE_SEGMENT_MATRIX,
    IDENTITY_POLICY,
    LIVE_VOICE_CONTRACT_VERSION,
    METRIC_DEFINITIONS,
    METRIC_SEMANTIC_MATRIX,
    OBSERVABILITY_SCHEMA_VERSION,
    OBSERVED_STATES,
    REASON_CODES,
    ROUTE_IMPLEMENTATION_CLASSES,
    SEGMENT_NAMES,
    SEGMENT_BINDING_MATRIX,
    TERMINAL_OUTCOMES,
    LiveVoiceObservabilityCollector,
    ObservabilityViolation,
    RouteDescriptor,
    create_metric,
    create_observation,
    create_queue_metric,
    create_route_descriptor,
    create_trace_binding,
    observation_from_task_event,
    observation_from_task_outbox,
    route_descriptor_from_route_record,
)


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "live_voice_observability_v1"
    / "contract.json"
)


def formal_route(
    owner: str = "runtime.conversation", provider: str = "jiuwenswarm-runtime"
) -> dict[str, object]:
    return {
        "implementation_class": "formal",
        "owner_module": owner,
        "capability_provider": provider,
        "contract_version": LIVE_VOICE_CONTRACT_VERSION,
        "reason_code": None,
    }


def fallback_route(route_class: str = "fallback") -> dict[str, object]:
    reasons = {
        "fallback": "ROUTE_FALLBACK",
        "demo_substitute": "DEMO_SUBSTITUTE",
        "unsupported": "UNSUPPORTED_CAPABILITY",
        "unknown": "UNKNOWN_PROVENANCE",
    }
    return {
        "implementation_class": route_class,
        "owner_module": None if route_class == "unknown" else "route.compatibility",
        "capability_provider": None,
        "contract_version": None,
        "reason_code": reasons[route_class],
    }


def observation(
    event_id: str,
    event_name: str,
    segment_name: str,
    *,
    binding: dict[str, object] | None = None,
    route: dict[str, object] | RouteDescriptor | None = None,
    **facts: object,
) -> dict[str, object]:
    default_binding: dict[str, object] = {"correlation_id": "corr-journey"}
    if segment_name in {"speech.capture", "speech.recognition"}:
        default_binding["interaction_id"] = "interaction-1"
    elif segment_name in {
        "speech.synthesis",
        "speech.playout",
        "runtime.response",
        "runtime.presentation",
    }:
        default_binding.update(
            interaction_id="interaction-1",
            response_id="response-1",
            response_generation=1,
        )
    elif segment_name == "runtime.turn":
        default_binding.update(interaction_id="interaction-1", turn_id="turn-1")
    elif segment_name.startswith("agent."):
        default_binding["round_id"] = "round-1"
    elif segment_name.startswith("task."):
        default_binding["task_id"] = "task-1"
        if segment_name == "task.attempt":
            default_binding["attempt_id"] = "attempt-1"
    return {
        "schema_version": OBSERVABILITY_SCHEMA_VERSION,
        "event_id": event_id,
        "event_name": event_name,
        "segment_name": segment_name,
        "observed_at": "2026-08-05T09:00:00Z",
        "monotonic_ms": 1000.0,
        "binding": binding or default_binding,
        "route": route or formal_route(),
        "source_component": "observability.test",
        **facts,
    }


def metric(
    measurement_id: str,
    metric_name: str,
    kind: str,
    unit: str,
    *,
    binding: dict[str, object] | None = None,
    segment_name: str | None = None,
    implementation_class: str = "formal",
    value: float = 1,
    **dimensions: object,
) -> dict[str, object]:
    default_binding: dict[str, object] = {"correlation_id": "corr-journey"}
    default_segment = "runtime.queue"
    semantic_dimensions: dict[str, object] = {}
    if metric_name == "live_voice.segment_latency_ms":
        default_binding.update(interaction_id="interaction-1", turn_id="turn-1")
        default_segment = "runtime.turn"
        semantic_dimensions["outcome"] = "completed"
    elif metric_name == "live_voice.cancel_total":
        default_binding["task_id"] = "task-1"
        default_segment = "task.command"
        semantic_dimensions.update(
            reason_code="CANCEL_REQUESTED", cancel_scope="task.cancel"
        )
    elif metric_name == "live_voice.stale_fence_total":
        default_binding.update(
            interaction_id="interaction-1",
            response_id="response-1",
            response_generation=1,
        )
        default_segment = "runtime.presentation"
        semantic_dimensions.update(reason_code="STALE_GENERATION", error_code="STALE")
    elif metric_name == "live_voice.task_total":
        default_binding["task_id"] = "task-1"
        default_segment = "task.progress"
        semantic_dimensions["outcome"] = "completed"
    elif metric_name == "live_voice.failure_total":
        default_binding["round_id"] = "round-1"
        default_segment = "agent.dispatch"
        semantic_dimensions.update(reason_code="AGENT_FAILURE", error_code="INTERNAL")
    elif metric_name == "live_voice.degradation_total":
        default_segment = "system.degradation"
        semantic_dimensions["reason_code"] = "DEGRADED"
    return {
        "schema_version": OBSERVABILITY_SCHEMA_VERSION,
        "measurement_id": measurement_id,
        "metric_name": metric_name,
        "metric_kind": kind,
        "unit": unit,
        "value": value,
        "observed_at": "2026-08-05T09:00:00Z",
        "binding": binding or default_binding,
        "route": formal_route(),
        "segment_name": segment_name or default_segment,
        "implementation_class": implementation_class,
        **semantic_dimensions,
        **dimensions,
    }


def json_semantic_matrix(
    matrix: Mapping[str, Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    return {
        name: {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in rule.items()
        }
        for name, rule in matrix.items()
    }


def test_python_matches_shared_observation_and_metric_fixture() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    event = create_observation(payload["observation"])
    measurement = create_metric(payload["metric"])

    assert event.to_dict() == payload["observation"]
    assert measurement.to_dict() == payload["metric"]
    vocabulary = payload["vocabulary"]
    assert list(ROUTE_IMPLEMENTATION_CLASSES) == vocabulary["route_classes"]
    assert list(CANCEL_SCOPES) == vocabulary["cancel_scopes"]
    assert list(SEGMENT_NAMES) == vocabulary["segments"]
    assert list(EVENT_NAMES) == vocabulary["events"]
    assert list(OBSERVED_STATES) == vocabulary["states"]
    assert list(TERMINAL_OUTCOMES) == vocabulary["outcomes"]
    assert list(ERROR_CODES) == vocabulary["error_codes"]
    assert list(REASON_CODES) == vocabulary["reason_codes"]
    assert {
        name: {"metric_kind": definition[0], "unit": definition[1]}
        for name, definition in METRIC_DEFINITIONS.items()
    } == vocabulary["metrics"]
    assert json_semantic_matrix(EVENT_SEMANTIC_MATRIX) == vocabulary["event_semantics"]
    assert (
        json_semantic_matrix(METRIC_SEMANTIC_MATRIX) == vocabulary["metric_semantics"]
    )
    assert {
        name: list(errors) for name, errors in FAILURE_ERROR_MATRIX.items()
    } == vocabulary["failure_error_matrix"]
    assert {
        name: list(segments) for name, segments in FAILURE_SEGMENT_MATRIX.items()
    } == vocabulary["failure_segment_matrix"]
    assert {
        name: list(bindings) for name, bindings in SEGMENT_BINDING_MATRIX.items()
    } == vocabulary["segment_binding_matrix"]
    assert (
        dict(CANCEL_TARGET_SEGMENT_MATRIX) == vocabulary["cancel_target_segment_matrix"]
    )
    assert {
        key: list(value) if isinstance(value, tuple) else value
        for key, value in IDENTITY_POLICY.items()
    } == vocabulary["identity_policy"]


def adversarial_payload(name: str) -> tuple[str, dict[str, object]]:
    if name == "capture_state_missing_state":
        return "observation", observation(
            "bad-capture-state", "speech.capture_state", "speech.capture"
        )
    if name == "completed_with_failure_truth":
        return "observation", observation(
            "bad-completed",
            "segment.completed",
            "runtime.response",
            outcome="failed",
            reason_code="AGENT_FAILURE",
            error_code="INTERNAL",
            duration_ms=1,
        )
    if name == "outbox_wrong_segment_missing_binding_source":
        return "observation", observation(
            "bad-outbox",
            "task.dispatch_outbox_observed",
            "speech.capture",
            binding={"correlation_id": "corr"},
        )
    if name == "segment_latency_with_failure_truth":
        return "metric", metric(
            "bad-latency",
            "live_voice.segment_latency_ms",
            "histogram",
            "milliseconds",
            outcome="failed",
            reason_code="TASK_FAILURE",
            error_code="INTERNAL",
        )
    identity, safe_suffix = {
        "identity_url": ("https://example.invalid/trace", "url"),
        "identity_api_key": ("api_key=private", "api"),
        "identity_secret": ("corr-secret-private", "marker"),
        "identity_transcript": ("complete transcript text", "text"),
    }[name]
    return "observation", observation(
        f"bad-identity-{safe_suffix}",
        "segment.started",
        "runtime.response",
        binding={"correlation_id": identity},
    )


def test_shared_adversarial_cases_fail_closed_with_zero_sink_effect() -> None:
    vocabulary = json.loads(FIXTURE.read_text(encoding="utf-8"))["vocabulary"]
    delivered: list[object] = []
    collector = LiveVoiceObservabilityCollector(
        observation_sink=delivered.append,
        metric_sink=delivered.append,
    )

    for case in vocabulary["adversarial_cases"]:
        kind, payload = adversarial_payload(case["name"])
        factory = create_observation if kind == "observation" else create_metric
        with pytest.raises(ObservabilityViolation) as captured:
            factory(payload)
        assert captured.value.reason == case["reason"]
        accepted = (
            collector.emit_observation(payload)
            if kind == "observation"
            else collector.emit_metric(payload)
        )
        assert accepted is False

    assert delivered == []
    assert collector.observations() == ()
    assert collector.metrics() == ()


def test_task_source_rules_require_exact_kind_identity_sequence_and_state() -> None:
    delivered: list[object] = []
    collector = LiveVoiceObservabilityCollector(observation_sink=delivered.append)
    missing_source = observation(
        "outbox-missing-source",
        "task.dispatch_outbox_observed",
        "task.queue",
        binding={
            "correlation_id": "corr",
            "task_id": "task-1",
            "attempt_id": "attempt-1",
        },
    )
    missing_target = observation(
        "outbox-missing-target",
        "task.dispatch_outbox_observed",
        "task.queue",
        binding={"correlation_id": "corr"},
        source_record_id="outbox-1",
        source_seq=1,
        state="pending",
    )
    wrong_source_kind = observation(
        "outbox-event-source",
        "task.cancel_outbox_observed",
        "task.queue",
        binding={
            "correlation_id": "corr",
            "task_id": "task-1",
            "attempt_id": "attempt-1",
        },
        source_event_id="event-1",
        source_occurred_at="2026-08-05T09:00:00Z",
        source_seq=1,
        state="pending",
    )
    for payload, reason in (
        (missing_source, "EVENT_FACT_REQUIRED"),
        (missing_target, "SEMANTIC_TARGET_BINDING_REQUIRED"),
        (wrong_source_kind, "EVENT_FACT_FORBIDDEN"),
    ):
        with pytest.raises(ObservabilityViolation) as captured:
            create_observation(payload)
        assert captured.value.reason == reason
        assert collector.emit_observation(payload) is False
    assert delivered == []


def test_metric_matrix_requires_exact_targets_with_zero_sink_effect() -> None:
    delivered: list[object] = []
    collector = LiveVoiceObservabilityCollector(metric_sink=delivered.append)
    cases = (
        (
            metric(
                "cancel-no-task",
                "live_voice.cancel_total",
                "counter",
                "count",
                binding={"correlation_id": "corr"},
            ),
            "CANCEL_TARGET_BINDING_REQUIRED",
        ),
        (
            metric(
                "fence-no-response",
                "live_voice.stale_fence_total",
                "counter",
                "count",
                binding={"correlation_id": "corr"},
            ),
            "SEMANTIC_TARGET_BINDING_REQUIRED",
        ),
        (
            metric(
                "task-no-task",
                "live_voice.task_total",
                "counter",
                "count",
                binding={"correlation_id": "corr"},
            ),
            "SEMANTIC_TARGET_BINDING_REQUIRED",
        ),
        (
            metric(
                "failure-no-round",
                "live_voice.failure_total",
                "counter",
                "count",
                binding={"correlation_id": "corr"},
            ),
            "FAILURE_TARGET_BINDING_REQUIRED",
        ),
        (
            metric(
                "agent-queue-no-round",
                "live_voice.queue_depth",
                "gauge",
                "items",
                binding={"correlation_id": "corr"},
                segment_name="agent.queue",
            ),
            "SEMANTIC_TARGET_BINDING_REQUIRED",
        ),
    )
    for payload, reason in cases:
        with pytest.raises(ObservabilityViolation) as captured:
            create_metric(payload)
        assert captured.value.reason == reason
        assert collector.emit_metric(payload) is False
    assert delivered == []


def test_one_journey_keeps_correlation_and_exact_identity_bindings() -> None:
    collector = LiveVoiceObservabilityCollector()
    bindings = [
        {
            "correlation_id": "corr-journey",
            "interaction_id": "interaction-1",
            "turn_id": "turn-1",
        },
        {
            "correlation_id": "corr-journey",
            "interaction_id": "interaction-1",
            "turn_id": "turn-1",
            "response_id": "response-1",
            "response_generation": 4,
        },
        {
            "correlation_id": "corr-journey",
            "interaction_id": "interaction-1",
            "turn_id": "turn-1",
            "response_id": "response-1",
            "response_generation": 4,
            "round_id": "round-1",
        },
        {
            "correlation_id": "corr-journey",
            "interaction_id": "interaction-1",
            "turn_id": "turn-1",
            "response_id": "response-1",
            "response_generation": 4,
            "round_id": "round-1",
            "task_id": "task-1",
            "attempt_id": "attempt-1",
        },
    ]
    segments = (
        "speech.recognition",
        "runtime.response",
        "agent.dispatch",
        "task.attempt",
    )
    for index, (binding, segment_name) in enumerate(
        zip(bindings, segments, strict=True)
    ):
        assert collector.emit_observation(
            observation(
                f"event-{index}",
                "segment.started",
                segment_name,
                binding=binding,
            )
        )

    journey = collector.by_correlation("corr-journey")
    assert [event.segment_name for event in journey] == list(segments)
    assert journey[-1].binding.to_dict() == bindings[-1]
    assert collector.by_correlation("other") == ()


@pytest.mark.parametrize(
    ("route_class", "reason"),
    [
        ("fallback", "ROUTE_FALLBACK"),
        ("demo_substitute", "DEMO_SUBSTITUTE"),
        ("unsupported", "UNSUPPORTED_CAPABILITY"),
        ("unknown", "UNKNOWN_PROVENANCE"),
    ],
)
def test_route_classes_remain_truthful_and_free_text_is_redacted(
    route_class: str, reason: str
) -> None:
    descriptor = route_descriptor_from_route_record(
        {
            "segment_id": "legacy-segment",
            "implementation_class": route_class,
            "owner_module": (
                None
                if route_class == "unknown"
                else "formal.adapters.browserSpeechRecognitionAdapter"
            ),
            "capability_provider": None,
            "contract_version": None,
            "correlation_id": "corr-1",
            "observed_at": "2026-08-05T09:00:00Z",
            "safe_reason": "Bearer secret-token and complete user request",
        }
    )

    assert descriptor.implementation_class == route_class
    assert descriptor.reason_code == reason
    assert "secret-token" not in json.dumps(descriptor.to_dict())


def test_cancel_fence_queue_failures_and_degradation_are_observable() -> None:
    collector = LiveVoiceObservabilityCollector()
    binding = {
        "correlation_id": "corr-fault",
        "interaction_id": "interaction-1",
        "response_id": "response-1",
        "response_generation": 7,
        "round_id": "round-1",
        "task_id": "task-1",
        "attempt_id": "attempt-1",
    }
    cases = [
        observation(
            "cancel-request",
            "cancel.requested",
            "runtime.response",
            binding=binding,
            reason_code="CANCEL_REQUESTED",
            cancel_scope="response.cancel",
        ),
        observation(
            "cancel-unknown",
            "cancel.result_unknown",
            "runtime.response",
            binding=binding,
            outcome="unknown",
            reason_code="CANCEL_RESULT_UNKNOWN",
            error_code="RESULT_UNKNOWN",
            cancel_scope="response.cancel",
        ),
        observation(
            "stale-fence",
            "fence.stale_dropped",
            "runtime.presentation",
            binding=binding,
            reason_code="STALE_GENERATION",
            error_code="STALE",
        ),
        observation(
            "queue-pressure",
            "queue.pressure",
            "agent.queue",
            binding=binding,
            reason_code="QUEUE_CAPACITY",
            queue_depth=8,
            queue_capacity=8,
        ),
        observation(
            "provider-failure",
            "failure.observed",
            "speech.recognition",
            binding=binding,
            reason_code="PROVIDER_FAILURE",
            error_code="UNAVAILABLE",
        ),
        observation(
            "agent-failure",
            "failure.observed",
            "agent.dispatch",
            binding=binding,
            reason_code="AGENT_FAILURE",
            error_code="INTERNAL",
        ),
        observation(
            "task-failure",
            "failure.observed",
            "task.attempt",
            binding=binding,
            reason_code="TASK_FAILURE",
            error_code="INTERNAL",
        ),
        observation(
            "degraded",
            "degradation.activated",
            "system.degradation",
            binding=binding,
            route=fallback_route(),
            reason_code="DEGRADED",
        ),
    ]

    assert all(collector.emit_observation(event) for event in cases)
    assert {event.reason_code for event in collector.observations()} >= {
        "CANCEL_REQUESTED",
        "CANCEL_RESULT_UNKNOWN",
        "STALE_GENERATION",
        "QUEUE_CAPACITY",
        "PROVIDER_FAILURE",
        "AGENT_FAILURE",
        "TASK_FAILURE",
        "DEGRADED",
    }


@pytest.mark.parametrize(
    ("cancel_scope", "segment_name", "binding"),
    [
        (
            "playback.stop",
            "speech.playout",
            {
                "correlation_id": "corr-cancel",
                "interaction_id": "interaction-1",
                "response_id": "response-1",
                "response_generation": 1,
            },
        ),
        (
            "response.cancel",
            "runtime.response",
            {
                "correlation_id": "corr-cancel",
                "interaction_id": "interaction-1",
                "response_id": "response-1",
                "response_generation": 1,
            },
        ),
        (
            "round.cancel",
            "agent.progress",
            {"correlation_id": "corr-cancel", "round_id": "round-1"},
        ),
        (
            "task.cancel",
            "task.command",
            {"correlation_id": "corr-cancel", "task_id": "task-1"},
        ),
    ],
)
def test_each_cancel_scope_requires_its_exact_target_and_has_zero_sink_on_reject(
    cancel_scope: str, segment_name: str, binding: dict[str, object]
) -> None:
    delivered: list[object] = []
    collector = LiveVoiceObservabilityCollector(observation_sink=delivered.append)

    assert collector.emit_observation(
        observation(
            f"accepted-{cancel_scope}",
            "cancel.requested",
            segment_name,
            binding=binding,
            reason_code="CANCEL_REQUESTED",
            cancel_scope=cancel_scope,
        )
    )
    assert not collector.emit_observation(
        observation(
            f"rejected-{cancel_scope}",
            "cancel.requested",
            segment_name,
            binding={"correlation_id": "corr-cancel"},
            reason_code="CANCEL_REQUESTED",
            cancel_scope=cancel_scope,
        )
    )
    assert len(delivered) == 1
    assert collector.stats().rejected_observations == 1


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        (
            observation(
                "bad-cancel",
                "cancel.requested",
                "runtime.response",
                binding={
                    "correlation_id": "corr",
                    "interaction_id": "interaction",
                    "response_id": "response",
                    "response_generation": 1,
                },
                reason_code="AGENT_FAILURE",
                cancel_scope="response.cancel",
            ),
            "EVENT_VALUE_MISMATCH",
        ),
        (
            observation(
                "bad-queue",
                "queue.pressure",
                "agent.queue",
                reason_code="QUEUE_CAPACITY",
                queue_depth=3,
                queue_capacity=4,
            ),
            "QUEUE_PRESSURE_INCOMPLETE",
        ),
        (
            observation(
                "bad-segment",
                "segment.failed",
                "agent.dispatch",
                duration_ms=1,
                reason_code="AGENT_FAILURE",
            ),
            "EVENT_FACT_REQUIRED",
        ),
        (
            observation(
                "bad-task-terminal",
                "task.state_observed",
                "task.progress",
                binding={"correlation_id": "corr", "task_id": "task-1"},
                source_event_id="task-event-1",
                source_occurred_at="2026-08-05T09:00:00Z",
                source_seq=1,
                state="terminal",
                outcome="failed",
                reason_code="PROVIDER_FAILURE",
            ),
            "SEMANTIC_TARGET_BINDING_REQUIRED",
        ),
        (
            observation(
                "bad-agent-failure-target",
                "failure.observed",
                "agent.dispatch",
                binding={"correlation_id": "corr"},
                reason_code="AGENT_FAILURE",
                error_code="INTERNAL",
            ),
            "FAILURE_TARGET_BINDING_REQUIRED",
        ),
        (
            observation(
                "bad-queue-segment",
                "queue.pressure",
                "runtime.response",
                reason_code="QUEUE_CAPACITY",
                queue_depth=4,
                queue_capacity=4,
            ),
            "EVENT_SEGMENT_MISMATCH",
        ),
    ],
)
def test_event_names_cannot_be_paired_with_misleading_facts(
    payload: dict[str, object], reason: str
) -> None:
    with pytest.raises(ObservabilityViolation) as captured:
        create_observation(payload)
    assert captured.value.reason == reason


def test_all_metric_definitions_are_closed_and_identity_is_not_a_dimension_map() -> (
    None
):
    with pytest.raises(TypeError):
        METRIC_DEFINITIONS["live_voice.user_text"] = (  # type: ignore[index]
            "counter",
            "count",
        )
    for index, (name, (kind, unit)) in enumerate(METRIC_DEFINITIONS.items()):
        measurement = create_metric(
            metric(
                f"metric-{index}",
                name,
                kind,
                unit,
            )
        )
        assert measurement.binding.correlation_id == "corr-journey"
        assert set(measurement.to_dict()).isdisjoint(
            {"labels", "attributes", "content"}
        )

    with pytest.raises(ObservabilityViolation) as captured:
        create_observation(
            observation(
                "cancel-without-scope",
                "cancel.requested",
                "runtime.response",
                binding={
                    "correlation_id": "corr",
                    "interaction_id": "interaction",
                    "response_id": "response",
                    "response_generation": 1,
                },
                reason_code="CANCEL_REQUESTED",
            )
        )
    assert captured.value.reason == "EVENT_FACT_REQUIRED"

    with pytest.raises(ObservabilityViolation) as captured:
        create_observation(
            observation(
                "stale-without-response",
                "fence.stale_dropped",
                "runtime.presentation",
                binding={"correlation_id": "corr"},
                reason_code="STALE_GENERATION",
                error_code="STALE",
            )
        )
    assert captured.value.reason == "SEMANTIC_TARGET_BINDING_REQUIRED"

    with pytest.raises(ObservabilityViolation, match="unknown fields"):
        create_metric(
            {
                **metric(
                    "metric-labels",
                    "live_voice.failure_total",
                    "counter",
                    "count",
                ),
                "labels": {"user_id": "unbounded"},
            }
        )
    with pytest.raises(ObservabilityViolation, match="not in the stable vocabulary"):
        create_metric(
            metric(
                "metric-reason",
                "live_voice.failure_total",
                "counter",
                "count",
                reason_code="USER_TEXT_AS_REASON",
            )
        )
    with pytest.raises(ObservabilityViolation) as captured:
        create_metric(
            metric(
                "metric-route-class",
                "live_voice.queue_depth",
                "gauge",
                "items",
                route={
                    **formal_route(),
                    "implementation_class": "fallback",
                    "reason_code": "ROUTE_FALLBACK",
                },
            )
        )
    assert captured.value.reason == "METRIC_ROUTE_CLASS_MISMATCH"


def test_sink_failures_and_reentrant_delivery_do_not_break_collection() -> None:
    delivered: list[str] = []
    collector: LiveVoiceObservabilityCollector

    def observation_sink(event: object) -> None:
        event_id = getattr(event, "event_id")
        delivered.append(event_id)
        if event_id == "outer":
            assert collector.emit_observation(
                observation("inner", "segment.started", "runtime.response")
            )
        if event_id == "raises":
            raise RuntimeError("sink unavailable")

    def metric_sink(_: object) -> None:
        raise RuntimeError("metric sink unavailable")

    collector = LiveVoiceObservabilityCollector(
        observation_sink=observation_sink, metric_sink=metric_sink
    )

    assert collector.emit_observation(
        observation("outer", "segment.started", "runtime.response")
    )
    assert collector.emit_observation(
        observation("raises", "segment.started", "runtime.response")
    )
    assert collector.emit_observation(
        observation(
            "after",
            "segment.completed",
            "runtime.response",
            outcome="completed",
            duration_ms=3,
        )
    )
    assert collector.emit_metric(
        metric("sink-metric", "live_voice.queue_depth", "gauge", "items")
    )
    assert [event.event_id for event in collector.observations()] == [
        "outer",
        "inner",
        "raises",
        "after",
    ]
    assert delivered == ["outer", "inner", "raises", "after"]
    assert collector.stats().sink_failures == 2


def test_disabled_collector_has_zero_validation_storage_or_sink_effect() -> None:
    effects: list[object] = []
    collector = LiveVoiceObservabilityCollector(
        enabled=False,
        observation_sink=effects.append,
        metric_sink=effects.append,
    )

    class Explosive:
        def __getattribute__(self, name: str) -> object:
            raise AssertionError(f"disabled collector inspected {name}")

    assert collector.emit_observation(Explosive()) is False
    assert collector.emit_metric(Explosive()) is False
    assert collector.observations() == ()
    assert collector.metrics() == ()
    assert collector.stats().accepted_observations == 0
    assert effects == []


def test_duplicate_ids_are_idempotent_and_conflicts_fail_closed_concurrently() -> None:
    delivered: list[str] = []
    collector = LiveVoiceObservabilityCollector(
        observation_sink=lambda event: delivered.append(event.event_id)
    )
    record = observation("same-id", "segment.started", "runtime.response")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(lambda _: collector.emit_observation(record), range(32))
        )

    assert all(results)
    assert len(collector.observations()) == 1
    assert delivered == ["same-id"]
    assert collector.stats().duplicate_observations == 31
    assert (
        collector.emit_observation(
            observation("same-id", "segment.started", "agent.dispatch")
        )
        is False
    )
    assert collector.stats().rejected_observations == 1


def test_collector_capacity_is_bounded_without_evicting_or_redelivering() -> None:
    delivered: list[str] = []
    collector = LiveVoiceObservabilityCollector(
        max_observations=1,
        max_metrics=1,
        observation_sink=lambda event: delivered.append(event.event_id),
        metric_sink=lambda measurement: delivered.append(measurement.measurement_id),
    )
    first_event = observation("event-first", "segment.started", "runtime.response")
    first_metric = metric("metric-first", "live_voice.queue_depth", "gauge", "items")

    assert collector.emit_observation(first_event)
    assert collector.emit_metric(first_metric)
    assert collector.emit_observation(first_event)
    assert collector.emit_metric(first_metric)
    assert not collector.emit_observation(
        observation("event-overflow", "segment.started", "runtime.response")
    )
    assert not collector.emit_metric(
        metric("metric-overflow", "live_voice.queue_depth", "gauge", "items")
    )
    assert [event.event_id for event in collector.observations()] == ["event-first"]
    assert [measurement.measurement_id for measurement in collector.metrics()] == [
        "metric-first"
    ]
    assert delivered == ["event-first", "metric-first"]
    assert collector.stats().duplicate_observations == 1
    assert collector.stats().duplicate_metrics == 1
    assert collector.stats().rejected_observations == 1
    assert collector.stats().rejected_metrics == 1

    with pytest.raises(ObservabilityViolation) as captured:
        LiveVoiceObservabilityCollector(max_observations=0)
    assert captured.value.reason == "INVALID_CAPACITY"


@pytest.mark.parametrize(
    ("binding", "reason"),
    [
        ({"correlation_id": "corr", "turn_id": "turn"}, "TURN_INTERACTION"),
        (
            {
                "correlation_id": "corr",
                "interaction_id": "interaction",
                "response_id": "response",
            },
            "RESPONSE_BINDING",
        ),
        ({"correlation_id": "corr", "attempt_id": "attempt"}, "ATTEMPT_TASK"),
    ],
)
def test_incomplete_identity_bindings_fail_closed(
    binding: dict[str, object], reason: str
) -> None:
    with pytest.raises(ObservabilityViolation) as captured:
        create_trace_binding(binding)
    assert captured.value.reason.startswith(reason)


def test_invalid_clock_free_text_and_unknown_fields_fail_closed() -> None:
    for bad_time in (
        "2026-08-05",
        "2026-08-05T09:00:00+00:00",
        "2026-02-30T09:00:00Z",
        "0000-08-05T09:00:00Z",
        "2026-08-05T09:00:00.1234567890Z",
    ):
        with pytest.raises(ObservabilityViolation) as captured:
            create_observation(
                {
                    **observation("clock", "segment.started", "runtime.response"),
                    "observed_at": bad_time,
                }
            )
        assert captured.value.reason == "INVALID_UTC_TIMESTAMP"
    with pytest.raises(ObservabilityViolation) as captured:
        create_route_descriptor(
            {
                **formal_route(),
                "capability_provider": "https://provider.example/?token=secret",
            }
        )
    assert captured.value.reason == "INVALID_STABLE_TOKEN"
    with pytest.raises(ObservabilityViolation) as captured:
        create_observation(
            {
                **observation("content", "segment.started", "runtime.response"),
                "user_content": "complete transcript",
            }
        )
    assert captured.value.reason == "UNKNOWN_FIELD"
    with pytest.raises(ObservabilityViolation) as captured:
        create_metric(
            metric(
                "unsafe-counter",
                "live_voice.failure_total",
                "counter",
                "count",
                value=9_007_199_254_740_992,
            )
        )
    assert captured.value.reason == "INVALID_COUNTER"
    with pytest.raises(ObservabilityViolation) as captured:
        create_observation(
            {
                **observation("source-conflict", "segment.started", "task.progress"),
                "source_event_id": "event-1",
                "source_record_id": "row-1",
            }
        )
    assert captured.value.reason == "SOURCE_KIND_CONFLICT"
    with pytest.raises(ObservabilityViolation) as captured:
        create_observation(
            {
                **observation("source-time", "segment.started", "task.progress"),
                "source_occurred_at": "2026-08-05T09:00:00Z",
            }
        )
    assert captured.value.reason == "SOURCE_EVENT_REQUIRED"
    with pytest.raises(ObservabilityViolation) as captured:
        create_observation(
            {
                **observation("bad-key", "segment.started", "runtime.response"),
                7: "not-a-json-key",
            }
        )
    assert captured.value.reason == "INVALID_OBJECT_KEY"


def test_collector_revalidates_forged_frozen_records_before_sink_delivery() -> None:
    delivered: list[object] = []
    collector = LiveVoiceObservabilityCollector(observation_sink=delivered.append)
    forged = create_observation(
        observation("forged", "segment.started", "runtime.response")
    )
    object.__setattr__(forged, "source_component", "complete user transcript")

    assert collector.emit_observation(forged) is False
    assert collector.observations() == ()
    assert collector.stats().rejected_observations == 1
    assert delivered == []


def test_task_event_mapper_preserves_source_identity_but_drops_details() -> None:
    event = PersistentTaskEvent(
        event_id="task-event-8",
        task_id="task-1",
        attempt_id="attempt-1",
        scope=ScopeRef(
            subject_id="subject-1",
            project_id="project-1",
            session_id="session-1",
            assurance=Assurance.AUTHENTICATED,
        ),
        seq=8,
        event_type="task.failed",
        state="terminal",
        outcome="failed",
        producer="task.core",
        source_event_id="executor-event-7",
        causation_id="command-1",
        correlation_id="corr-task",
        occurred_at="2026-08-05T09:00:00Z",
        details={"summary": "private user content", "error": "credential-like text"},
    )

    observed = observation_from_task_event(
        event,
        observation_id="obs-task-event-8",
        observed_at="2026-08-05T09:00:01Z",
        monotonic_ms=55.0,
        route=create_route_descriptor(
            formal_route("task.core", "project-code-executor")
        ),
    )

    assert observed.binding.task_id == "task-1"
    assert observed.binding.attempt_id == "attempt-1"
    assert observed.source_event_id == "task-event-8"
    assert observed.source_occurred_at == "2026-08-05T09:00:00Z"
    assert observed.observed_at == "2026-08-05T09:00:01Z"
    assert observed.source_seq == 8
    assert observed.state == "terminal"
    assert observed.outcome == "failed"
    assert observed.reason_code == "TASK_FAILURE"
    serialized = json.dumps(observed.to_dict())
    assert "private user content" not in serialized
    assert "credential-like text" not in serialized


def test_task_outbox_mapper_uses_public_identity_state_and_never_reads_spec() -> None:
    class ExplosiveSpec:
        def __getattribute__(self, name: str) -> object:
            raise AssertionError(f"outbox mapper inspected private spec field {name}")

    scope = ScopeRef(
        subject_id="subject-1",
        project_id="project-1",
        session_id="session-1",
        assurance=Assurance.AUTHENTICATED,
    )
    private_spec = ExplosiveSpec()
    task = PersistentTaskRecord(
        task_id="task-1",
        scope=scope,
        spec=private_spec,  # type: ignore[arg-type]
        state=FormalTaskState.ACCEPTED,
        attempt_id="attempt-1",
        correlation_id="corr-task",
        cancel_requested=False,
        dispatch_fenced=False,
        outcome=None,
        reconciliation_state=None,
        reconciliation_reason=None,
    )
    item = PersistentOutboxItem(
        outbox_id="outbox-1",
        kind=OutboxKind.ATTEMPT_DISPATCH,
        task_id="task-1",
        attempt_id="attempt-1",
        command_id="command-1",
        scope=scope,
        spec=private_spec,  # type: ignore[arg-type]
        executor_ref=None,
        source_seq=1,
        state=OutboxState.PENDING,
        delivery_count=0,
    )

    observed = observation_from_task_outbox(
        item,
        task,
        observation_id="obs-outbox-1",
        observed_at="2026-08-05T09:00:02Z",
        monotonic_ms=80,
        route=formal_route("task.core", "project-code-executor"),
    )

    assert observed.event_name == "task.dispatch_outbox_observed"
    assert observed.segment_name == "task.queue"
    assert observed.binding.task_id == "task-1"
    assert observed.binding.attempt_id == "attempt-1"
    assert observed.source_event_id is None
    assert observed.source_record_id == "outbox-1"
    assert observed.source_seq == 1
    assert observed.state == "pending"
    assert "instruction" not in json.dumps(observed.to_dict())

    mismatched = PersistentOutboxItem(
        outbox_id="outbox-2",
        kind=OutboxKind.ATTEMPT_CANCEL,
        task_id="task-1",
        attempt_id="foreign-attempt",
        command_id="command-2",
        scope=scope,
        spec=private_spec,  # type: ignore[arg-type]
        executor_ref=None,
        source_seq=2,
        state=OutboxState.CLAIMED,
        delivery_count=1,
    )
    with pytest.raises(ObservabilityViolation) as captured:
        observation_from_task_outbox(
            mismatched,
            task,
            observation_id="obs-outbox-2",
            observed_at="2026-08-05T09:00:03Z",
            monotonic_ms=90,
            route=formal_route("task.core", "project-code-executor"),
        )
    assert captured.value.reason == "TASK_OUTBOX_BINDING_MISMATCH"


def test_queue_snapshot_helper_emits_only_bounded_gauge_dimensions() -> None:
    route = create_route_descriptor(formal_route("agent.bridge", "jiuwenswarm-agent"))
    measurement = create_queue_metric(
        measurement_id="metric-agent-depth-1",
        binding={"correlation_id": "corr-agent", "round_id": "round-1"},
        route=route,
        observed_at="2026-08-05T09:00:00Z",
        segment_name="agent.queue",
        depth=7,
    )

    assert measurement.metric_name == "live_voice.queue_depth"
    assert measurement.value == 7
    assert measurement.segment_name == "agent.queue"
    assert measurement.implementation_class == "formal"
