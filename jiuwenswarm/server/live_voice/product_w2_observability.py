# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Default-off product owner for the local W2 correlated evidence plane."""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from datetime import UTC, datetime
from typing import Final

from jiuwenswarm.server.live_voice.observability import (
    LIVE_VOICE_CONTRACT_VERSION,
    OBSERVABILITY_SCHEMA_VERSION,
    create_observation,
)
from jiuwenswarm.server.live_voice.product_composition_contract import (
    ProductEvidenceId,
    ProductRouteFact,
    ProductRouteReason,
    ProductRouteTruth,
    ProductSegment,
)
from jiuwenswarm.server.live_voice.product_composition_root import (
    ProductCompositionContext,
)
from jiuwenswarm.server.live_voice.product_observability_adapter import (
    ActiveProductObservabilityActivation,
    ProductObservabilityActivationEvidence,
    ProductObservabilityLeaseCloseError,
    activate_product_observability_adapter,
)
from jiuwenswarm.server.live_voice.project_code_executor import (
    DIRECT_PROJECT_EXECUTOR_REF_PREFIX,
    FORMAL_PROJECT_EXECUTOR_ID,
)
from jiuwenswarm.server.live_voice.formal_task_models import (
    FormalAttemptState,
    PersistentAttemptRecord,
    PersistentTaskEvent,
)
from jiuwenswarm.server.live_voice.w2_evidence_exporter import (
    DEFAULT_W2_EVIDENCE_MAX_RECORDS,
    W2JsonlEvidenceExporter,
    create_w2_evidence_exporter,
    verify_w2_candidate_checkout,
)


W2_EVIDENCE_ENABLE_ENV: Final = "JIUWENSWARM_LIVE_VOICE_W2_EVIDENCE_ENABLED"
W2_EVIDENCE_PATH_ENV: Final = "JIUWENSWARM_LIVE_VOICE_W2_EVIDENCE_PATH"
W2_GATEWAY_EVIDENCE_PATH_ENV: Final = "JIUWENSWARM_LIVE_VOICE_W2_GATEWAY_EVIDENCE_PATH"
W2_EVIDENCE_PRIVATE_KEY_PATH_ENV: Final = (
    "JIUWENSWARM_LIVE_VOICE_W2_EVIDENCE_PRIVATE_KEY_PATH"
)
W2_EVIDENCE_SIGNATURE_PATH_ENV: Final = (
    "JIUWENSWARM_LIVE_VOICE_W2_EVIDENCE_SIGNATURE_PATH"
)
W2_GATEWAY_EVIDENCE_PRIVATE_KEY_PATH_ENV: Final = (
    "JIUWENSWARM_LIVE_VOICE_W2_GATEWAY_EVIDENCE_PRIVATE_KEY_PATH"
)
W2_GATEWAY_EVIDENCE_SIGNATURE_PATH_ENV: Final = (
    "JIUWENSWARM_LIVE_VOICE_W2_GATEWAY_EVIDENCE_SIGNATURE_PATH"
)
W2_EVIDENCE_CAPACITY_ENV: Final = "JIUWENSWARM_LIVE_VOICE_W2_EVIDENCE_CAPACITY"
W2_CANDIDATE_SHA_ENV: Final = "JIUWENSWARM_LIVE_VOICE_W2_CANDIDATE_SHA"
W2_ENVIRONMENT_ID_ENV: Final = "JIUWENSWARM_LIVE_VOICE_W2_ENVIRONMENT_ID"
W2_SESSION_ID_ENV: Final = "JIUWENSWARM_LIVE_VOICE_W2_SESSION_ID"
W2_MODE_ID_ENV: Final = "JIUWENSWARM_LIVE_VOICE_W2_MODE_ID"
W2_REPOSITORY_PATH_ENV: Final = "JIUWENSWARM_LIVE_VOICE_W2_REPOSITORY_PATH"
W2_EVIDENCE_SET_ID_ENV: Final = "JIUWENSWARM_LIVE_VOICE_W2_EVIDENCE_SET_ID"
W2_ARTIFACT_ID_ENV: Final = "JIUWENSWARM_LIVE_VOICE_W2_ARTIFACT_ID"
W2_GATEWAY_ARTIFACT_ID_ENV: Final = "JIUWENSWARM_LIVE_VOICE_W2_GATEWAY_ARTIFACT_ID"
W2_ARTIFACT_SEQUENCE_ENV: Final = "JIUWENSWARM_LIVE_VOICE_W2_ARTIFACT_SEQUENCE"
W2_GATEWAY_ARTIFACT_SEQUENCE_ENV: Final = (
    "JIUWENSWARM_LIVE_VOICE_W2_GATEWAY_ARTIFACT_SEQUENCE"
)
W2_PROCESS_EPOCH_ENV: Final = "JIUWENSWARM_LIVE_VOICE_W2_PROCESS_EPOCH"
W2_GATEWAY_PROCESS_EPOCH_ENV: Final = "JIUWENSWARM_LIVE_VOICE_W2_GATEWAY_PROCESS_EPOCH"
W2_PREDECESSOR_ARTIFACT_ID_ENV: Final = (
    "JIUWENSWARM_LIVE_VOICE_W2_PREDECESSOR_ARTIFACT_ID"
)
W2_GATEWAY_PREDECESSOR_ARTIFACT_ID_ENV: Final = (
    "JIUWENSWARM_LIVE_VOICE_W2_GATEWAY_PREDECESSOR_ARTIFACT_ID"
)

_PRODUCT_SEGMENTS: Final = {
    # Each entry names only stages that the exact successful product result
    # proves. Lease/control-plane calls intentionally emit no positive W2
    # evidence. A committed P2 submit returns both its caller-owned turn_id and
    # the canonical Agent round_id, so those two stages can be observed
    # independently without inventing either identity from the RPC request id.
    "media.capture": ("speech.capture",),
    "media.playout.receipt": ("speech.playout",),
    "media.downlink": ("runtime.queue",),
    "media.duplex.receipt": ("runtime.queue",),
    "speech.recognize.batch": ("speech.recognition",),
    "speech.synthesize.batch": ("speech.synthesis",),
    "live_voice.composition.p2.activate": ("runtime.queue",),
    "live_voice.composition.p2.close": ("runtime.queue",),
    "live_voice.composition.p2.submit": ("runtime.turn", "agent.dispatch"),
    "live_voice.composition.p2.notification.next": ("agent.progress",),
    "live_voice.composition.p2.presentation.ack": ("runtime.presentation",),
    "live_voice.composition.p2.barge_in": ("speech.playout",),
    "live_voice.composition.p3.mutate": ("task.command",),
    "live_voice.composition.p3.progress.ack": ("task.progress",),
    "task.create": ("task.command",),
    "task.cancel": ("task.command",),
    "task.retry": ("task.command",),
    "task.get": ("task.progress",),
    "task.status": ("task.progress",),
    "task.events": ("task.progress",),
    "task.list": ("runtime.queue",),
}

_PRODUCT_SOURCES: Final = {
    "media.capture": "product.w2.media.capture",
    "media.playout.receipt": "product.w2.browser.playout",
    "media.downlink": "product.w2.media.downlink",
    "media.duplex.receipt": "product.w2.media.duplex",
    "speech.recognize.batch": "product.w2.speech.recognize",
    "speech.synthesize.batch": "product.w2.speech.synthesize",
    "live_voice.composition.p2.activate": "product.w2.p2.activate",
    "live_voice.composition.p2.close": "product.w2.p2.close",
    "live_voice.composition.p2.notification.next": "product.w2.p2.notification",
    "live_voice.composition.p2.presentation.ack": "product.w2.p2.presentation",
    "live_voice.composition.p2.barge_in": "product.w2.p2.barge",
    "task.create": "product.w2.task.create",
    "task.cancel": "product.w2.task.cancel",
    "task.retry": "product.w2.task.retry",
    "task.get": "product.w2.task.get",
    "task.status": "product.w2.task.status",
    "task.events": "product.w2.task.events",
    "task.list": "product.w2.task.list",
}

_GATEWAY_OPERATIONS: Final = frozenset(
    {
        "media.capture",
        "media.playout.receipt",
        "media.downlink",
        "media.duplex.receipt",
        "speech.recognize.batch",
        "speech.synthesize.batch",
    }
)
_AGENTSERVER_OPERATIONS: Final = frozenset(_PRODUCT_SEGMENTS) - _GATEWAY_OPERATIONS


def _operation_source(operation: str, *, task_operation: str | None) -> str | None:
    if operation == "live_voice.composition.p2.submit":
        return "product.w2.p2.submit.agent"
    if operation == "live_voice.composition.p3.mutate":
        return None if task_operation is None else f"product.w2.{task_operation}"
    if operation == "live_voice.composition.p3.progress.ack":
        return "product.w2.p3.progress"
    return _PRODUCT_SOURCES.get(operation)


def _enabled(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _failure_facts(segment_name: str, error_code: str | None) -> tuple[str, str] | None:
    if not isinstance(error_code, str):
        return None
    if error_code == "TIMEOUT":
        return "TIMEOUT", error_code
    if error_code in {"CAPABILITY_UNAVAILABLE", "UNAVAILABLE"}:
        return "UNAVAILABLE", error_code
    if error_code in {
        "INVALID_ARGUMENT",
        "UNSUPPORTED",
        "CONFLICT",
        "STALE",
        "PROTOCOL_VIOLATION",
    }:
        return "PROTOCOL_REJECTED", error_code
    if error_code in {"CANCELLED", "RESULT_UNKNOWN"}:
        return None
    if segment_name.startswith("task."):
        return "TASK_FAILURE", error_code
    if segment_name.startswith("agent."):
        return "AGENT_FAILURE", error_code
    return None


def product_result_task_id(
    params: object, payload: object
) -> tuple[str | None, str | None]:
    """Project exact task/attempt identity from closed product envelopes."""

    containers: list[object] = [params, payload]
    if isinstance(payload, dict):
        containers.extend(
            payload.get(key)
            for key in (
                "result",
                "formal_task_result",
                "task",
                "attempt",
                "progress",
            )
        )
        result = payload.get("result")
        if isinstance(result, dict):
            containers.extend(
                result.get(key)
                for key in ("formal_task_result", "task", "attempt", "progress")
            )
    task_id: str | None = None
    attempt_id: str | None = None
    for container in containers:
        if not isinstance(container, dict):
            continue
        if task_id is None and isinstance(container.get("task_id"), str):
            task_id = container["task_id"]
        if attempt_id is None and isinstance(container.get("attempt_id"), str):
            attempt_id = container["attempt_id"]
    return task_id, attempt_id


def product_result_error_code(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, dict) and isinstance(error.get("code"), str):
        return error["code"]
    result = payload.get("result")
    if isinstance(result, dict):
        nested = result.get("error")
        if isinstance(nested, dict) and isinstance(nested.get("code"), str):
            return nested["code"]
    return None


def product_result_response_binding(
    params: object, payload: object
) -> tuple[str | None, str | None, int | None]:
    containers: list[object] = [params, payload]
    for owner in (params, payload):
        if not isinstance(owner, dict):
            continue
        containers.extend(owner.get(key) for key in ("response", "result"))
        result = owner.get("result")
        if isinstance(result, dict):
            containers.append(result.get("response"))
    interaction_id: str | None = None
    response_id: str | None = None
    response_generation: int | None = None
    for container in containers:
        if not isinstance(container, dict):
            continue
        response = container.get("response")
        if isinstance(response, dict):
            container = response
        if interaction_id is None and isinstance(container.get("interaction_id"), str):
            interaction_id = container["interaction_id"]
        if response_id is None and isinstance(container.get("response_id"), str):
            response_id = container["response_id"]
        if (
            response_generation is None
            and type(container.get("response_generation")) is int
        ):
            response_generation = container["response_generation"]
    return interaction_id, response_id, response_generation


def product_result_execution_binding(
    params: object, payload: object
) -> tuple[str | None, str | None]:
    """Project only real turn/round identities from closed product results."""

    containers: list[object] = [params, payload]
    if isinstance(payload, dict):
        containers.append(payload.get("result"))
    turn_id: str | None = None
    round_id: str | None = None
    for container in containers:
        if not isinstance(container, dict):
            continue
        if turn_id is None and isinstance(container.get("turn_id"), str):
            turn_id = container["turn_id"]
        if round_id is None and isinstance(container.get("round_id"), str):
            round_id = container["round_id"]
    return turn_id, round_id


def product_result_agent_output_kind(payload: object) -> str | None:
    """Project only canonical Jiuwen Agent/Tool output classes."""

    if not isinstance(payload, dict):
        return None
    result = payload.get("result")
    if not isinstance(result, dict) or result.get("status") != "notification":
        return None
    event = result.get("agent_event")
    if not isinstance(event, dict):
        return None
    event_type = event.get("event_type")
    if event_type == "chat.tool_call":
        return "tool_call"
    if event_type == "chat.tool_result":
        return "tool_result"
    if event_type == "chat.final" and isinstance(result.get("presentation_unit"), dict):
        return "final"
    return None


def product_result_task_event_facts(payload: object) -> tuple[dict[str, object], ...]:
    """Extract content-free TaskEvent authority facts from task.events only."""

    if not isinstance(payload, dict):
        return ()
    result = payload.get("result")
    if not isinstance(result, dict):
        return ()
    events = result.get("events")
    if not isinstance(events, list) or len(events) > 4_096:
        return ()
    facts: list[dict[str, object]] = []
    for event in events:
        if not isinstance(event, dict):
            return ()
        required = (
            "event_id",
            "task_id",
            "attempt_id",
            "seq",
            "state",
            "outcome",
            "correlation_id",
            "occurred_at",
        )
        if any(key not in event for key in required):
            return ()
        if (
            not all(
                isinstance(event[key], str) and bool(event[key].strip())
                for key in (
                    "event_id",
                    "task_id",
                    "attempt_id",
                    "state",
                    "correlation_id",
                    "occurred_at",
                )
            )
            or type(event["seq"]) is not int
        ):
            return ()
        outcome = event["outcome"]
        if outcome is not None and not isinstance(outcome, str):
            return ()
        facts.append(
            {
                "event_id": event["event_id"],
                "task_id": event["task_id"],
                "attempt_id": event["attempt_id"],
                "seq": event["seq"],
                "state": event["state"],
                "outcome": outcome,
                "correlation_id": event["correlation_id"],
                "occurred_at": event["occurred_at"],
            }
        )
    return tuple(facts)


def product_result_observation_ok(
    operation: str, *, result_ok: bool, payload: object
) -> bool:
    """Reject successful envelopes that do not prove the claimed product effect."""

    if result_ok is not True or not isinstance(payload, dict):
        return False
    result = payload.get("result")
    if not isinstance(result, dict):
        return False
    if operation == "live_voice.composition.p2.activate":
        return (
            result.get("status") == "active"
            and isinstance(result.get("activation_id"), str)
            and type(result.get("activation_generation")) is int
        )
    if operation == "live_voice.composition.p2.close":
        return result.get("status") == "closed"
    if operation == "live_voice.composition.p2.submit":
        return bool(
            (
                result.get("status") == "round_accepted"
                and isinstance(result.get("round_id"), str)
                and isinstance(result.get("response"), dict)
            )
            or (
                result.get("status") == "task_origin_accepted"
                and isinstance(result.get("turn_id"), str)
                and isinstance(result.get("commit_id"), str)
            )
        )
    if operation == "live_voice.composition.p2.notification.next":
        return result.get("status") == "notification" and isinstance(
            result.get("round_id"), str
        )
    if operation == "live_voice.composition.p2.presentation.ack":
        return (
            result.get("status") == "presentation_acknowledged"
            and result.get("accepted") is True
        )
    if operation == "live_voice.composition.p2.barge_in":
        effect_ids = result.get("effect_ids")
        return (
            result.get("status") == "barge_in_applied"
            and result.get("applied") is True
            and isinstance(effect_ids, list)
            and "playback.stop" in effect_ids
        )
    if operation == "live_voice.composition.p3.mutate":
        return (
            result.get("status") == "mutation_processed"
            and result.get("operation") in {"task.create", "task.cancel", "task.retry"}
            and isinstance(result.get("formal_task_result"), dict)
        )
    if operation == "live_voice.composition.p3.progress.ack":
        return (
            result.get("status") == "acknowledged"
            and result.get("acknowledgement") == "web_ui_text_consumed"
            and isinstance(result.get("task_id"), str)
        )
    return True


def product_result_voice_task_origin(payload: object) -> bool:
    """Recognize only the accepted Speech-bound turn reserved for Task."""

    if not isinstance(payload, dict):
        return False
    result = payload.get("result")
    return bool(
        isinstance(result, dict)
        and result.get("status") == "task_origin_accepted"
        and isinstance(result.get("turn_id"), str)
        and bool(result["turn_id"].strip())
        and isinstance(result.get("commit_id"), str)
        and bool(result["commit_id"].strip())
    )


def product_result_voice_task_bridge(params: object, payload: object) -> bool:
    """Recognize only a successful P3 create bound to committed voice origin."""

    if not isinstance(params, dict) or not isinstance(payload, dict):
        return False
    result = payload.get("result")
    formal_result = (
        result.get("formal_task_result") if isinstance(result, dict) else None
    )
    return bool(
        params.get("operation") == "task.create"
        and params.get("source") == "voice"
        and isinstance(params.get("turn_id"), str)
        and bool(params["turn_id"].strip())
        and isinstance(params.get("commit_id"), str)
        and bool(params["commit_id"].strip())
        and isinstance(result, dict)
        and result.get("status") == "mutation_processed"
        and result.get("operation") == "task.create"
        and isinstance(formal_result, dict)
        and isinstance(formal_result.get("task_id"), str)
        and bool(formal_result["task_id"].strip())
    )


def product_result_has_terminal_d0_attempt(payload: object) -> bool:
    """Recognize only an exact terminal result from the formal direct executor."""

    if not isinstance(payload, dict):
        return False
    result = payload.get("result")
    if not isinstance(result, dict):
        return False
    attempt = result.get("attempt")
    if not isinstance(attempt, dict) or set(attempt) != {
        "attempt_id",
        "task_id",
        "executor_id",
        "executor_ref",
        "state",
        "outcome",
        "source_seq",
    }:
        return False
    attempt_id = attempt.get("attempt_id")
    task_id = attempt.get("task_id")
    outcome = attempt.get("outcome")
    return (
        isinstance(attempt_id, str)
        and bool(attempt_id.strip())
        and isinstance(task_id, str)
        and bool(task_id.strip())
        and attempt.get("executor_id") == FORMAL_PROJECT_EXECUTOR_ID
        and attempt.get("executor_ref")
        == f"{DIRECT_PROJECT_EXECUTOR_REF_PREFIX}{attempt_id}"
        and attempt.get("state") == "terminal"
        # D0 positive evidence means the real project executor completed.  A
        # terminal failure remains observable through the ordinary task.status
        # record, but can never mint the successful task.attempt score path.
        and outcome == "completed"
        and type(attempt.get("source_seq")) is int
        and attempt["source_seq"] >= 0
    )


def _formal_route_fact(
    evidence: ProductObservabilityActivationEvidence,
) -> ProductRouteFact:
    if (
        not evidence.worker_started
        or not evidence.lease_open
        or evidence.segment is not ProductSegment.OBSERVABILITY
    ):
        raise ValueError("formal W2 observability evidence is incomplete")
    return ProductRouteFact(
        segment=ProductSegment.OBSERVABILITY,
        truth=ProductRouteTruth.FORMAL,
        reason_id=ProductRouteReason.FORMAL_ROUTE_OBSERVED,
        evidence_ids=(
            ProductEvidenceId.TRUSTED_AUTHORITY_RESOLVED,
            ProductEvidenceId.FORMAL_ACTIVATION_LEASE_OPEN,
            ProductEvidenceId.RUNTIME_PATH_OBSERVED,
        ),
        formal_runtime_observed=True,
    )


class ProductW2ObservabilityOwner:
    """Pin one exact integrated route to the sanitized local JSONL sink."""

    def __init__(
        self,
        exporter: W2JsonlEvidenceExporter,
        *,
        expected_session_id: str,
        producer_id: str,
    ) -> None:
        if type(exporter) is not W2JsonlEvidenceExporter:
            raise ValueError("W2 product observability requires the exact local sink")
        self._exporter = exporter
        self._expected_session_id = expected_session_id
        if producer_id not in {"gateway", "agentserver"}:
            raise ValueError("W2 observability producer_id is invalid")
        self._producer_id = producer_id
        self._allowed_operations = (
            _GATEWAY_OPERATIONS if producer_id == "gateway" else _AGENTSERVER_OPERATIONS
        )
        self._activation: ActiveProductObservabilityActivation | None = None
        self._context: ProductCompositionContext | None = None
        self._lock = asyncio.Lock()
        self._closed = False
        self._active_task_id: str | None = None
        self._active_task_attempt_id: str | None = None

    async def observe_route(
        self,
        *,
        session_id: str,
        correlation_id: str,
        request_id: str,
        operation: str,
        result_ok: bool,
        task_id: str | None = None,
        attempt_id: str | None = None,
        interaction_id: str | None = None,
        response_id: str | None = None,
        response_generation: int | None = None,
        turn_id: str | None = None,
        round_id: str | None = None,
        error_code: str | None = None,
        terminal_d0_attempt: bool = False,
        voice_task_bridge: bool = False,
        voice_task_origin: bool = False,
        task_operation: str | None = None,
        agent_output_kind: str | None = None,
        task_event_facts: tuple[dict[str, object], ...] = (),
    ) -> bool:
        """Emit outcome-aware, content-free formal route facts."""

        async with self._lock:
            if (
                task_id is None
                and operation.startswith("live_voice.composition.p2.")
                and self._active_task_id is not None
            ):
                task_id = self._active_task_id
                attempt_id = self._active_task_attempt_id
            segment_names = _PRODUCT_SEGMENTS.get(operation)
            if (
                self._closed
                or segment_names is None
                or operation not in self._allowed_operations
                or session_id != self._expected_session_id
                or type(terminal_d0_attempt) is not bool
                or type(voice_task_bridge) is not bool
                or type(voice_task_origin) is not bool
            ):
                return False
            if task_operation not in {None, "task.create", "task.cancel", "task.retry"}:
                return False
            if agent_output_kind not in {None, "tool_call", "tool_result", "final"}:
                return False
            if type(task_event_facts) is not tuple:
                return False
            if result_ok:
                if operation == "live_voice.composition.p2.submit":
                    fact_specs = (
                        (("runtime.turn", "product.voice_task_origin"),)
                        if voice_task_origin
                        else (
                            ("runtime.turn", "product.w2.p2.submit.agent"),
                            ("agent.dispatch", "product.w2.p2.submit.agent"),
                        )
                    )
                elif operation == "live_voice.composition.p3.mutate":
                    if task_operation is None:
                        return False
                    fact_specs = (
                        ("task.command", f"product.w2.{task_operation}"),
                        *(
                            (("task.command", "product.voice_task_bridge"),)
                            if voice_task_bridge
                            else ()
                        ),
                    )
                elif operation == "live_voice.composition.p3.progress.ack":
                    fact_specs = (
                        ("task.progress", "product.w2.p3.progress"),
                        ("task.progress", "product.w2.p3.ui"),
                    )
                elif operation == "live_voice.composition.p2.notification.next":
                    fact_specs = (
                        (
                            "agent.progress",
                            (
                                f"product.w2.agent.{agent_output_kind}"
                                if agent_output_kind is not None
                                else "product.w2.p2.notification"
                            ),
                        ),
                    )
                elif operation == "media.playout.receipt":
                    fact_specs = (("speech.playout", "product.w2.browser.playout"),)
                else:
                    source_component = _PRODUCT_SOURCES.get(operation)
                    if source_component is None:
                        return False
                    fact_specs = tuple(
                        (segment_name, source_component)
                        for segment_name in segment_names
                    )
            else:
                failure_source = _operation_source(
                    operation, task_operation=task_operation
                )
                if failure_source is None:
                    return False
                fact_specs = tuple(
                    (segment_name, failure_source) for segment_name in segment_names
                )
            observed_segments = tuple(segment for segment, _ in fact_specs)
            request_fingerprint = (
                "w2-request-"
                + hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:32]
            )
            if (
                any(name.startswith("task.") for name in observed_segments)
                and not task_id
            ):
                # A task route without exact task identity cannot prove P3.
                return False
            if (
                any(
                    name in {"speech.capture", "speech.recognition", "runtime.turn"}
                    for name in observed_segments
                )
                and not interaction_id
            ):
                return False
            if any(
                name in {"speech.synthesis", "speech.playout", "runtime.presentation"}
                for name in observed_segments
            ) and (
                not interaction_id
                or not response_id
                or not isinstance(response_generation, int)
                or response_generation < 0
            ):
                return False
            if not result_ok and self._activation is None:
                # A denied request must neither mint positive route evidence nor
                # pin the candidate correlation ahead of a valid route.
                return False
            if self._activation is None:
                context = ProductCompositionContext(session_id, correlation_id)
                activation = await activate_product_observability_adapter(
                    enabled=True,
                    context=context,
                    exporter=self._exporter.exporter,
                    formal_route_fact_issuer=_formal_route_fact,
                )
                if not isinstance(activation, ActiveProductObservabilityActivation):
                    return False
                self._activation = activation
                self._context = context
            context = self._context
            activation = self._activation
            if (
                context is None
                or activation is None
                or context.session_id != session_id
                or context.correlation_id != correlation_id
            ):
                return False
            if result_ok:
                observations = []
                for segment_name, source_component in fact_specs:
                    if segment_name == "runtime.turn" and not turn_id:
                        return False
                    if segment_name.startswith("agent.") and not round_id:
                        return False
                    # Preserve every identity actually returned by the closed
                    # product operation.  Gate joins are exact-field joins;
                    # correlation alone is never promoted into causality.
                    binding: dict[str, object] = {"correlation_id": correlation_id}
                    if interaction_id is not None:
                        binding["interaction_id"] = interaction_id
                    if turn_id is not None:
                        binding["turn_id"] = turn_id
                    if response_id is not None:
                        binding["response_id"] = response_id
                        binding["response_generation"] = response_generation
                    if round_id is not None:
                        binding["round_id"] = round_id
                    if task_id is not None:
                        binding["task_id"] = task_id
                        if attempt_id is not None:
                            binding["attempt_id"] = attempt_id
                    route = {
                        "implementation_class": "formal",
                        "owner_module": (
                            "gateway.live_voice"
                            if segment_name.startswith("speech.")
                            else "product.composition"
                        ),
                        "capability_provider": (
                            "formal-dedicated-media"
                            if operation.startswith("media.")
                            else (
                                "formal-batch-speech"
                                if segment_name.startswith("speech.")
                                else (
                                    "jiuwenswarm-task-core"
                                    if segment_name.startswith("task.")
                                    else "jiuwenswarm-agent-runtime"
                                )
                            )
                        ),
                        "contract_version": LIVE_VOICE_CONTRACT_VERSION,
                        "reason_code": None,
                    }
                    common = {
                        "schema_version": OBSERVABILITY_SCHEMA_VERSION,
                        "segment_name": segment_name,
                        "observed_at": datetime.now(UTC)
                        .isoformat()
                        .replace("+00:00", "Z"),
                        "monotonic_ms": time.monotonic() * 1_000,
                        "binding": binding,
                        "route": route,
                        "source_component": source_component,
                    }
                    segment_token = hashlib.sha256(
                        (
                            f"{request_fingerprint}:{segment_name}:{source_component}"
                        ).encode("utf-8")
                    ).hexdigest()[:24]
                    if operation == "live_voice.composition.p2.barge_in":
                        observations.append(
                            create_observation(
                                {
                                    **common,
                                    "event_id": f"w2-cancel-{segment_token}",
                                    "event_name": "cancel.acknowledged",
                                    "source_record_id": request_fingerprint,
                                    "reason_code": "CANCEL_ACKNOWLEDGED",
                                    "cancel_scope": "playback.stop",
                                }
                            )
                        )
                    else:
                        observations.extend(
                            (
                                create_observation(
                                    {
                                        **common,
                                        "event_id": f"w2-route-{segment_token}",
                                        "event_name": "route.selected",
                                        "source_record_id": request_fingerprint,
                                    }
                                ),
                                create_observation(
                                    {
                                        **common,
                                        "event_id": f"w2-complete-{segment_token}",
                                        "event_name": "segment.completed",
                                        "source_record_id": request_fingerprint,
                                        "state": "terminal",
                                        "outcome": "completed",
                                        "duration_ms": 0.0,
                                    }
                                ),
                            )
                        )
                if (
                    terminal_d0_attempt
                    and operation == "task.status"
                    and segment_names == ("task.progress",)
                    and task_id is not None
                    and attempt_id is not None
                ):
                    attempt_common = {
                        **common,
                        "segment_name": "task.attempt",
                        "source_component": "product.w2.task.d0",
                        "binding": {
                            "correlation_id": correlation_id,
                            **(
                                {"interaction_id": interaction_id}
                                if interaction_id is not None
                                else {}
                            ),
                            **({"turn_id": turn_id} if turn_id is not None else {}),
                            "task_id": task_id,
                            "attempt_id": attempt_id,
                        },
                    }
                    observations.extend(
                        (
                            create_observation(
                                {
                                    **attempt_common,
                                    "event_id": (
                                        f"w2-route-task-attempt-{request_fingerprint}"
                                    ),
                                    "event_name": "route.selected",
                                    "source_record_id": request_fingerprint,
                                }
                            ),
                            create_observation(
                                {
                                    **attempt_common,
                                    "event_id": (
                                        "w2-complete-task-attempt-"
                                        f"{request_fingerprint}"
                                    ),
                                    "event_name": "segment.completed",
                                    "source_record_id": request_fingerprint,
                                    "state": "terminal",
                                    "outcome": "completed",
                                    "duration_ms": 0.0,
                                }
                            ),
                        )
                    )
                if operation == "task.events":
                    for event in task_event_facts:
                        if (
                            event.get("task_id") != task_id
                            or event.get("correlation_id") != correlation_id
                            or not isinstance(event.get("attempt_id"), str)
                        ):
                            return False
                        task_event_binding = {
                            "correlation_id": correlation_id,
                            "task_id": task_id,
                            "attempt_id": event["attempt_id"],
                        }
                        observations.append(
                            create_observation(
                                {
                                    **common,
                                    "segment_name": "task.progress",
                                    "binding": task_event_binding,
                                    "source_component": "product.w2.task.event",
                                    "event_id": (
                                        "w2-task-event-"
                                        + hashlib.sha256(
                                            str(event["event_id"]).encode("utf-8")
                                        ).hexdigest()[:32]
                                    ),
                                    "event_name": "task.state_observed",
                                    "source_event_id": event["event_id"],
                                    "source_occurred_at": event["occurred_at"],
                                    "source_seq": event["seq"],
                                    "state": event["state"],
                                    "outcome": event["outcome"],
                                }
                            )
                        )
                accepted = all(
                    activation.adapter.consume_observation(
                        context=context,
                        observation=observation,
                    ).accepted_for_export
                    for observation in observations
                )
                if (
                    accepted
                    and operation == "live_voice.composition.p3.mutate"
                    and task_operation == "task.create"
                    and task_id is not None
                ):
                    self._active_task_id = task_id
                    self._active_task_attempt_id = attempt_id
                if accepted and task_id == self._active_task_id:
                    terminal = any(
                        event.get("task_id") == task_id
                        and event.get("attempt_id") == self._active_task_attempt_id
                        and event.get("state") == "terminal"
                        for event in task_event_facts
                    )
                    cancelled = (
                        operation == "live_voice.composition.p3.mutate"
                        and task_operation == "task.cancel"
                    )
                    if terminal or cancelled:
                        self._active_task_id = None
                        self._active_task_attempt_id = None
                return accepted
            # A failed multi-stage call is attributed only to its narrowest
            # terminal segment. It cannot mint any positive evidence.
            segment_name = segment_names[-1]
            binding: dict[str, object] = {"correlation_id": correlation_id}
            if interaction_id is not None:
                binding["interaction_id"] = interaction_id
            if turn_id is not None:
                binding["turn_id"] = turn_id
            if response_id is not None:
                binding["response_id"] = response_id
                binding["response_generation"] = response_generation
            if round_id is not None:
                binding["round_id"] = round_id
            if task_id is not None:
                binding["task_id"] = task_id
                if attempt_id is not None:
                    binding["attempt_id"] = attempt_id
            common = {
                "schema_version": OBSERVABILITY_SCHEMA_VERSION,
                "segment_name": segment_name,
                "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "monotonic_ms": time.monotonic() * 1_000,
                "binding": binding,
                "route": {
                    "implementation_class": "formal",
                    "owner_module": "product.composition",
                    "capability_provider": "jiuwenswarm-formal-runtime",
                    "contract_version": LIVE_VOICE_CONTRACT_VERSION,
                    "reason_code": None,
                },
                "source_component": _operation_source(
                    operation, task_operation=task_operation
                ),
            }
            if common["source_component"] is None:
                return False
            failure = _failure_facts(segment_name, error_code)
            if failure is None:
                return False
            reason_code, public_error_code = failure
            failed = create_observation(
                {
                    **common,
                    "event_id": f"w2-failed-{request_fingerprint}",
                    "event_name": "segment.failed",
                    "source_record_id": request_fingerprint,
                    "state": "failed",
                    "outcome": "failed",
                    "reason_code": reason_code,
                    "error_code": public_error_code,
                    "duration_ms": 0.0,
                }
            )
            return activation.adapter.consume_observation(
                context=context,
                observation=failed,
            ).accepted_for_export

    async def observe_reconciliation_event(
        self,
        event: object,
        attempt: object,
    ) -> bool:
        """Export one exact durable startup-reconciliation TaskEvent.

        The typed Store event and its persisted Attempt binding are required;
        callers cannot mint restart credit from a summary counter or RPC body.
        """

        if (
            self._producer_id != "agentserver"
            or type(event) is not PersistentTaskEvent
            or type(attempt) is not PersistentAttemptRecord
            or event.event_type != "task.terminal"
            or event.state != "terminal"
            or event.outcome is None
            or event.scope.session_id != self._expected_session_id
            or event.task_id != attempt.task_id
            or event.attempt_id != attempt.attempt_id
            or attempt.executor_id != FORMAL_PROJECT_EXECUTOR_ID
            or attempt.executor_ref
            != f"{DIRECT_PROJECT_EXECUTOR_REF_PREFIX}{attempt.attempt_id}"
            or attempt.state is not FormalAttemptState.TERMINAL
            or attempt.outcome is None
            or event.outcome != attempt.outcome.value
            or event.producer not in {"task_core", "task_core.reconciliation"}
        ):
            return False
        async with self._lock:
            if self._closed:
                return False
            if self._activation is None:
                context = ProductCompositionContext(
                    self._expected_session_id, event.correlation_id
                )
                activation = await activate_product_observability_adapter(
                    enabled=True,
                    context=context,
                    exporter=self._exporter.exporter,
                    formal_route_fact_issuer=_formal_route_fact,
                )
                if not isinstance(activation, ActiveProductObservabilityActivation):
                    return False
                self._activation = activation
                self._context = context
            context = self._context
            activation = self._activation
            if (
                context is None
                or activation is None
                or context.session_id != self._expected_session_id
                or context.correlation_id != event.correlation_id
            ):
                return False
            token = hashlib.sha256(event.event_id.encode("utf-8")).hexdigest()[:32]
            observation = create_observation(
                {
                    "schema_version": OBSERVABILITY_SCHEMA_VERSION,
                    "segment_name": "task.progress",
                    "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    "monotonic_ms": time.monotonic() * 1_000,
                    "binding": {
                        "correlation_id": event.correlation_id,
                        "task_id": event.task_id,
                        "attempt_id": event.attempt_id,
                    },
                    "route": {
                        "implementation_class": "formal",
                        "owner_module": "server.live_voice.persistent_task_core",
                        "capability_provider": "direct-project-code-executor",
                        "contract_version": LIVE_VOICE_CONTRACT_VERSION,
                        "reason_code": None,
                    },
                    "source_component": "product.w2.task.reconciliation",
                    "event_id": f"w2-reconciliation-{token}",
                    "event_name": "task.state_observed",
                    "source_event_id": event.event_id,
                    "source_occurred_at": event.occurred_at,
                    "source_seq": event.seq,
                    "state": event.state,
                    "outcome": event.outcome,
                }
            )
            return activation.adapter.consume_observation(
                context=context,
                observation=observation,
            ).accepted_for_export

    async def close(self) -> None:
        async with self._lock:
            self._closed = True
            activation = self._activation
            if activation is None:
                return
            try:
                result = await activation.lease.close_with_result()
            except ProductObservabilityLeaseCloseError:
                raise
            if result.retained_for_retry:
                self._closed = False
                raise RuntimeError("W2 observability cleanup remains pending")
            await self._exporter.seal()
            self._activation = None
            self._context = None
            self._active_task_id = None
            self._active_task_attempt_id = None


def create_product_w2_observability_owner_from_environment() -> (
    ProductW2ObservabilityOwner | None
):
    """Create no path, sink, buffer, or worker unless the feature is explicit."""

    if not _enabled(os.getenv(W2_EVIDENCE_ENABLE_ENV)):
        return None
    raw_capacity = str(os.getenv(W2_EVIDENCE_CAPACITY_ENV) or "").strip()
    capacity = (
        DEFAULT_W2_EVIDENCE_MAX_RECORDS if not raw_capacity else int(raw_capacity)
    )
    private_key_path = os.getenv(W2_EVIDENCE_PRIVATE_KEY_PATH_ENV)
    signature_path = os.getenv(W2_EVIDENCE_SIGNATURE_PATH_ENV)
    if not private_key_path or not signature_path:
        raise ValueError("enabled AgentServer W2 evidence requires producer signing")
    verify_w2_candidate_checkout(
        repository_path=os.getenv(W2_REPOSITORY_PATH_ENV),
        candidate_sha=os.getenv(W2_CANDIDATE_SHA_ENV),
        bind_loaded_source=True,
    )
    exporter = create_w2_evidence_exporter(
        enabled=True,
        path=os.getenv(W2_EVIDENCE_PATH_ENV),
        max_records=capacity,
        candidate_sha=os.getenv(W2_CANDIDATE_SHA_ENV),
        environment_id=os.getenv(W2_ENVIRONMENT_ID_ENV),
        session_id=os.getenv(W2_SESSION_ID_ENV),
        mode_id=os.getenv(W2_MODE_ID_ENV),
        evidence_set_id=os.getenv(W2_EVIDENCE_SET_ID_ENV),
        artifact_id=os.getenv(W2_ARTIFACT_ID_ENV),
        artifact_sequence=int(str(os.getenv(W2_ARTIFACT_SEQUENCE_ENV) or "")),
        producer_id="agentserver",
        process_epoch=os.getenv(W2_PROCESS_EPOCH_ENV),
        predecessor_artifact_id=os.getenv(W2_PREDECESSOR_ARTIFACT_ID_ENV),
        repository_path=os.getenv(W2_REPOSITORY_PATH_ENV),
        signing_private_key_path=private_key_path,
        signature_path=signature_path,
    )
    if type(exporter) is not W2JsonlEvidenceExporter:
        raise RuntimeError("enabled W2 evidence did not create its exact sink")
    expected_session_id = str(os.getenv(W2_SESSION_ID_ENV) or "")
    return ProductW2ObservabilityOwner(
        exporter,
        expected_session_id=expected_session_id,
        producer_id="agentserver",
    )


def create_gateway_w2_observability_owner_from_environment() -> (
    ProductW2ObservabilityOwner | None
):
    """Create the Gateway P1 evidence plane on its own append-only path."""

    if not _enabled(os.getenv(W2_EVIDENCE_ENABLE_ENV)):
        return None
    raw_capacity = str(os.getenv(W2_EVIDENCE_CAPACITY_ENV) or "").strip()
    capacity = (
        DEFAULT_W2_EVIDENCE_MAX_RECORDS if not raw_capacity else int(raw_capacity)
    )
    private_key_path = os.getenv(W2_GATEWAY_EVIDENCE_PRIVATE_KEY_PATH_ENV)
    signature_path = os.getenv(W2_GATEWAY_EVIDENCE_SIGNATURE_PATH_ENV)
    if not private_key_path or not signature_path:
        raise ValueError("enabled Gateway W2 evidence requires producer signing")
    verify_w2_candidate_checkout(
        repository_path=os.getenv(W2_REPOSITORY_PATH_ENV),
        candidate_sha=os.getenv(W2_CANDIDATE_SHA_ENV),
        bind_loaded_source=True,
    )
    exporter = create_w2_evidence_exporter(
        enabled=True,
        path=os.getenv(W2_GATEWAY_EVIDENCE_PATH_ENV),
        max_records=capacity,
        candidate_sha=os.getenv(W2_CANDIDATE_SHA_ENV),
        environment_id=os.getenv(W2_ENVIRONMENT_ID_ENV),
        session_id=os.getenv(W2_SESSION_ID_ENV),
        mode_id=os.getenv(W2_MODE_ID_ENV),
        evidence_set_id=os.getenv(W2_EVIDENCE_SET_ID_ENV),
        artifact_id=os.getenv(W2_GATEWAY_ARTIFACT_ID_ENV),
        artifact_sequence=int(str(os.getenv(W2_GATEWAY_ARTIFACT_SEQUENCE_ENV) or "")),
        producer_id="gateway",
        process_epoch=os.getenv(W2_GATEWAY_PROCESS_EPOCH_ENV),
        predecessor_artifact_id=os.getenv(W2_GATEWAY_PREDECESSOR_ARTIFACT_ID_ENV),
        repository_path=os.getenv(W2_REPOSITORY_PATH_ENV),
        signing_private_key_path=private_key_path,
        signature_path=signature_path,
    )
    if type(exporter) is not W2JsonlEvidenceExporter:
        raise RuntimeError("enabled Gateway W2 evidence did not create its exact sink")
    return ProductW2ObservabilityOwner(
        exporter,
        expected_session_id=str(os.getenv(W2_SESSION_ID_ENV) or ""),
        producer_id="gateway",
    )


__all__ = [
    "ProductW2ObservabilityOwner",
    "W2_EVIDENCE_CAPACITY_ENV",
    "W2_EVIDENCE_ENABLE_ENV",
    "W2_EVIDENCE_PATH_ENV",
    "W2_EVIDENCE_PRIVATE_KEY_PATH_ENV",
    "W2_EVIDENCE_SIGNATURE_PATH_ENV",
    "W2_GATEWAY_EVIDENCE_PATH_ENV",
    "W2_GATEWAY_EVIDENCE_PRIVATE_KEY_PATH_ENV",
    "W2_GATEWAY_EVIDENCE_SIGNATURE_PATH_ENV",
    "W2_CANDIDATE_SHA_ENV",
    "W2_ENVIRONMENT_ID_ENV",
    "W2_SESSION_ID_ENV",
    "W2_MODE_ID_ENV",
    "W2_REPOSITORY_PATH_ENV",
    "W2_EVIDENCE_SET_ID_ENV",
    "W2_ARTIFACT_ID_ENV",
    "W2_GATEWAY_ARTIFACT_ID_ENV",
    "W2_ARTIFACT_SEQUENCE_ENV",
    "W2_GATEWAY_ARTIFACT_SEQUENCE_ENV",
    "W2_PROCESS_EPOCH_ENV",
    "W2_GATEWAY_PROCESS_EPOCH_ENV",
    "W2_PREDECESSOR_ARTIFACT_ID_ENV",
    "W2_GATEWAY_PREDECESSOR_ARTIFACT_ID_ENV",
    "product_result_error_code",
    "product_result_execution_binding",
    "product_result_agent_output_kind",
    "product_result_task_event_facts",
    "product_result_has_terminal_d0_attempt",
    "product_result_observation_ok",
    "product_result_response_binding",
    "product_result_task_id",
    "product_result_voice_task_bridge",
    "product_result_voice_task_origin",
    "create_product_w2_observability_owner_from_environment",
    "create_gateway_w2_observability_owner_from_environment",
]
