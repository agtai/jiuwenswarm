# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
from jiuwenswarm.server.live_voice.observability import (
    LIVE_VOICE_CONTRACT_VERSION,
    OBSERVABILITY_SCHEMA_VERSION,
    LiveVoiceMetric,
    LiveVoiceObservation,
    create_metric,
    create_observation,
)
from jiuwenswarm.server.live_voice.live_voice_configuration_declaration import (
    LIVE_VOICE_CONFIGURATION_CONTRACT_VERSION,
    AuthenticationMode,
    DurabilityLevel,
    ExecutorCapability,
    LiveVoiceCapability,
    LiveVoiceDeploymentProfile,
    ValidatedAuthenticationConfiguration,
    ValidatedExecutorConfiguration,
    ValidatedLiveVoiceConfiguration,
)
from jiuwenswarm.server.live_voice.observability_correlation_contract import (
    CorrelationEvaluationReason,
    evaluate_observability_correlation_map,
)
from jiuwenswarm.server.live_voice.observability_otel_codec import (
    OtelBackendSignalKind,
)
from jiuwenswarm.server.live_voice.product_authority import (
    ResolvedProductAuthority,
)
from jiuwenswarm.server.live_voice.product_observability_runtime import (
    BoundedInMemoryOtelBackend,
    PRODUCT_OBSERVABILITY_BACKEND_ENV,
    PRODUCT_OBSERVABILITY_BACKEND_ID,
    PRODUCT_OBSERVABILITY_ENABLE_ENV,
    PRODUCT_OBSERVABILITY_TOKEN_KEY_ENV,
    ProductDiagnosticIdentity,
    ProductDiagnosticSeam,
    ProductObservabilityRuntime,
    ProductObservabilityRuntimeError,
    ProductObservabilityRuntimeState,
    TrustedCorrelationProjectionOwner,
    create_product_observability_runtime_from_environment,
)


CORRELATION_ID = "correlation-runtime-1"
SESSION_ID = "session-runtime-1"
PROJECT_ID = "project-runtime-1"
SUBJECT_ID = "principal-runtime-1"


def _formal_route() -> dict[str, object]:
    return {
        "implementation_class": "formal",
        "owner_module": "product.composition.registry",
        "capability_provider": "jiuwenswarm-runtime",
        "contract_version": LIVE_VOICE_CONTRACT_VERSION,
        "reason_code": None,
    }


def _observation(
    event_id: str,
    *,
    correlation_id: str = CORRELATION_ID,
) -> LiveVoiceObservation:
    return create_observation(
        {
            "schema_version": OBSERVABILITY_SCHEMA_VERSION,
            "event_id": event_id,
            "event_name": "task.state_observed",
            "segment_name": "task.progress",
            "observed_at": "2026-08-21T10:00:00Z",
            "monotonic_ms": 10.0,
            "binding": {
                "correlation_id": correlation_id,
                "interaction_id": "interaction-1",
                "response_id": "response-1",
                "response_generation": 3,
                "task_id": "task-1",
                "attempt_id": "attempt-1",
            },
            "route": _formal_route(),
            "source_component": "task.core",
            "source_event_id": "event-authority-1",
            "source_occurred_at": "2026-08-21T09:59:59Z",
            "source_seq": 4,
            "state": "running",
        }
    )


def _metric(measurement_id: str) -> LiveVoiceMetric:
    return create_metric(
        {
            "schema_version": OBSERVABILITY_SCHEMA_VERSION,
            "measurement_id": measurement_id,
            "metric_name": "live_voice.queue_depth",
            "metric_kind": "gauge",
            "unit": "items",
            "value": 2,
            "observed_at": "2026-08-21T10:00:00Z",
            "binding": {
                "correlation_id": CORRELATION_ID,
                "task_id": "task-1",
                "attempt_id": "attempt-1",
            },
            "route": _formal_route(),
            "segment_name": "task.queue",
            "implementation_class": "formal",
        }
    )


def _authority(
    *,
    correlation_id: str = CORRELATION_ID,
    subject_id: str = SUBJECT_ID,
    project_id: str = PROJECT_ID,
) -> ResolvedProductAuthority:
    scope = ScopeRef(
        subject_id,
        project_id,
        SESSION_ID,
        Assurance.AUTHENTICATED,
    )
    return ResolvedProductAuthority(
        principal_id=subject_id,
        session_id=SESSION_ID,
        project_id=project_id,
        scope=scope,
        operation="agent.chat",
        capabilities=frozenset({"agent.chat"}),
        expires_at="2030-01-01T00:00:00Z",
        assurance=Assurance.AUTHENTICATED,
        source="server.auth.session",
        correlation_id=correlation_id,
    )


def _enable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PRODUCT_OBSERVABILITY_ENABLE_ENV, "1")
    monkeypatch.setenv(
        PRODUCT_OBSERVABILITY_BACKEND_ENV,
        PRODUCT_OBSERVABILITY_BACKEND_ID,
    )
    monkeypatch.setenv(PRODUCT_OBSERVABILITY_TOKEN_KEY_ENV, "4a" * 32)


def _validated_configuration(
    backend: BoundedInMemoryOtelBackend,
) -> ValidatedLiveVoiceConfiguration:
    provider = backend.validated_provider_configuration()
    digest = hashlib.sha256(b"test-owning-adapters-v1").hexdigest()
    return ValidatedLiveVoiceConfiguration(
        contract_version=LIVE_VOICE_CONFIGURATION_CONTRACT_VERSION,
        configuration_id="test.owning-adapters.v1",
        configuration_digest=digest,
        profile=LiveVoiceDeploymentProfile.FORMAL_LIVE_VOICE,
        enabled=True,
        ordinary_production_default_off=True,
        authentication=ValidatedAuthenticationConfiguration(
            mode=AuthenticationMode.SCOPED_BEARER,
            validation_receipt_id="test-auth-owner.v1",
            scope_digest=hashlib.sha256(b"test-auth-scope").hexdigest(),
        ),
        executor=ValidatedExecutorConfiguration(
            executor_id="direct-project-code",
            adapter_id="live-voice.direct-project-code",
            durability_level=DurabilityLevel.D2,
            capabilities=tuple(sorted(ExecutorCapability, key=lambda item: item.value)),
            validation_receipt_id="test-executor-owner.v1",
            configuration_digest=hashlib.sha256(b"test-executor").hexdigest(),
        ),
        providers=(provider,),
        capabilities=tuple(
            sorted(
                (
                    LiveVoiceCapability.AUTHENTICATED,
                    LiveVoiceCapability.EXECUTOR_D2,
                    LiveVoiceCapability.FORMAL_WEB,
                    LiveVoiceCapability.TASK_MUTATION,
                    LiveVoiceCapability.TASK_QUERY,
                    LiveVoiceCapability.TELEMETRY_EXPORT,
                ),
                key=lambda item: item.value,
            )
        ),
    )


def _runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    backend_capacity: int = 256,
) -> tuple[ProductObservabilityRuntime, BoundedInMemoryOtelBackend]:
    _enable(monkeypatch)
    backend = BoundedInMemoryOtelBackend(capacity=backend_capacity)
    runtime = create_product_observability_runtime_from_environment(
        backend=backend,
        validated_configuration=_validated_configuration(backend),
    )
    assert type(runtime) is ProductObservabilityRuntime
    return runtime, backend


def test_feature_off_returns_before_touching_backend_or_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PoisonBackend:
        def __getattribute__(self, name: str) -> object:
            raise AssertionError(f"feature-off touched backend {name}")

    monkeypatch.delenv(PRODUCT_OBSERVABILITY_ENABLE_ENV, raising=False)
    monkeypatch.setenv(PRODUCT_OBSERVABILITY_BACKEND_ENV, "wrong")
    monkeypatch.setenv(PRODUCT_OBSERVABILITY_TOKEN_KEY_ENV, "secret-value")

    result = create_product_observability_runtime_from_environment(
        backend=PoisonBackend(),  # type: ignore[arg-type]
        validated_configuration=object(),
    )

    assert result is None


@pytest.mark.parametrize(
    ("backend_id", "key"),
    [
        ("", "4a" * 32),
        ("collector", "4a" * 32),
        (PRODUCT_OBSERVABILITY_BACKEND_ID, ""),
        (PRODUCT_OBSERVABILITY_BACKEND_ID, "abcd"),
        (PRODUCT_OBSERVABILITY_BACKEND_ID, "not-hex"),
    ],
)
def test_missing_or_invalid_selection_and_trust_anchor_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    backend_id: str,
    key: str,
) -> None:
    monkeypatch.setenv(PRODUCT_OBSERVABILITY_ENABLE_ENV, "1")
    monkeypatch.setenv(PRODUCT_OBSERVABILITY_BACKEND_ENV, backend_id)
    monkeypatch.setenv(PRODUCT_OBSERVABILITY_TOKEN_KEY_ENV, key)
    backend = BoundedInMemoryOtelBackend()

    with pytest.raises(ProductObservabilityRuntimeError):
        create_product_observability_runtime_from_environment(
            backend=backend,
            validated_configuration=object(),
        )

    assert backend.health().state is ProductObservabilityRuntimeState.CREATED
    assert backend.health().accepted == backend.health().rejected == 0


@pytest.mark.asyncio
async def test_started_runtime_exports_recanonical_span_and_bounded_metric_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, backend = _runtime(monkeypatch)
    await runtime.start()
    assert runtime.bind_authority(_authority()) is True

    await runtime.export(_observation("runtime-event-1"))
    await runtime.export(_metric("runtime-metric-1"))

    span, metric = backend.records()
    span_payload = json.loads(span.record.canonical_bytes.decode("ascii"))
    metric_payload = json.loads(metric.record.canonical_bytes.decode("ascii"))
    assert span.record.signal_kind is OtelBackendSignalKind.SPAN_EVENT
    assert span.trace_identities
    assert all(
        type(value) is int or str(value).startswith("lvpub:")
        for _, value in span.trace_identities
    )
    assert set(span_payload["attributes"]) == {
        "live_voice.implementation_class",
        "live_voice.segment_name",
        "live_voice.state",
    }
    assert span_payload["trace"]["parent_span_id"] is None
    assert {
        (link["cause_kind"], link["effect_kind"])
        for link in span_payload["trace"]["causation"]
    }.issuperset({("subject", "project"), ("project", "session")})
    assert metric.record.signal_kind is OtelBackendSignalKind.METRIC_POINT
    assert metric.trace_identities == ()
    assert "trace" not in metric_payload
    assert set(metric_payload["attributes"]) == {
        "live_voice.implementation_class",
        "live_voice.segment_name",
    }
    serialized = b"\n".join(
        envelope.record.canonical_bytes for envelope in backend.records()
    )
    for forbidden in (
        CORRELATION_ID,
        SESSION_ID,
        PROJECT_ID,
        SUBJECT_ID,
        b"task-1".decode(),
        "attempt-1",
        "response-1",
    ):
        assert forbidden.encode() not in serialized

    health = runtime.health()
    assert health.ready is True
    assert health.backend.ready is True
    assert not hasattr(health, "exporter")
    closed = await runtime.close()
    assert closed.state is ProductObservabilityRuntimeState.CLOSED
    assert closed.ready is False
    assert closed.authority_bindings == closed.diagnostic_identities == 0


@pytest.mark.asyncio
async def test_complete_diagnostic_chain_is_trace_only_and_seam_locatable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, backend = _runtime(monkeypatch)
    await runtime.start()
    assert runtime.bind_authority(_authority())
    expected_seams = set(ProductDiagnosticSeam)
    for index, seam in enumerate(ProductDiagnosticSeam):
        source = _observation(f"chain-record-{index}")
        identity = ProductDiagnosticIdentity(
            seam=seam,
            seam_id=f"seam-source-{index}",
            command_id="command-1",
            event_id="event-1",
            outbox_id="outbox-1",
            executor_id="executor-1",
            checkpoint_id="checkpoint-1",
            effect_id="effect-1",
            presentation_id="presentation-1",
        )
        assert runtime.register_diagnostic_identity(
            source.event_id,
            identity,
            correlation_id=CORRELATION_ID,
        )
        await runtime.export(source)

    assert {record.seam for record in backend.records()} == expected_seams
    trace_keys = {key for key, _ in backend.records()[0].trace_identities}
    assert {
        "subject_id",
        "project_id",
        "session_id",
        "correlation_id",
        "interaction_id",
        "response_id",
        "response_generation",
        "task_id",
        "attempt_id",
        "command_id",
        "event_id",
        "outbox_id",
        "executor_id",
        "checkpoint_id",
        "effect_id",
        "presentation_id",
        "seam_id",
    }.issubset(trace_keys)
    complete_payload = json.loads(
        backend.records()[0].record.canonical_bytes.decode("ascii")
    )
    causation_edges = {
        (link["cause_kind"], link["effect_kind"])
        for link in complete_payload["trace"]["causation"]
    }
    assert {
        ("task", "attempt"),
        ("task", "command"),
        ("command", "outbox"),
        ("outbox", "executor"),
        ("executor", "checkpoint"),
        ("executor", "effect"),
        ("response", "presentation"),
    }.issubset(causation_edges)
    await runtime.close()


@pytest.mark.asyncio
async def test_diagnostic_identity_is_bound_to_its_exact_correlation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, backend = _runtime(monkeypatch)
    await runtime.start()
    second_correlation = "correlation-second"
    assert runtime.bind_authority(_authority())
    assert runtime.bind_authority(_authority(correlation_id=second_correlation))
    source_id = "shared-source-record"
    assert runtime.register_diagnostic_identity(
        source_id,
        ProductDiagnosticIdentity(
            seam=ProductDiagnosticSeam.COMMAND,
            seam_id="owner-command-seam",
            command_id="command-1",
        ),
        correlation_id=CORRELATION_ID,
    )

    await runtime.export(_observation(source_id))
    await runtime.export(_observation(source_id, correlation_id=second_correlation))

    first, second = backend.records()
    assert first.seam is ProductDiagnosticSeam.COMMAND
    assert second.seam is ProductDiagnosticSeam.RESPONSE
    assert "command_id" in dict(first.trace_identities)
    assert "command_id" not in dict(second.trace_identities)
    await runtime.close()


@pytest.mark.asyncio
async def test_exact_replay_is_idempotent_and_conflict_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, backend = _runtime(monkeypatch)
    await runtime.start()
    assert runtime.bind_authority(_authority())
    source = _observation("replay-source")

    await runtime.export(source)
    await runtime.export(source)
    conflicting_payload = source.to_dict()
    conflicting_payload["state"] = "blocked"
    with pytest.raises(ProductObservabilityRuntimeError):
        await runtime.export(create_observation(conflicting_payload))

    assert len(backend.records()) == 1
    assert runtime.health().delivered_records == 1
    assert runtime.health().idempotent_replays == 1
    assert runtime.health().rejected_replays == 1
    await runtime.close()


def test_receipt_requires_the_injected_owner_not_an_attacker_key() -> None:
    owner = TrustedCorrelationProjectionOwner(b"owner-key" * 4)
    attacker = TrustedCorrelationProjectionOwner(b"other-key" * 4)
    dimensions = _metric("metric-dimensions")
    labels = tuple()
    from jiuwenswarm.server.live_voice.observability_correlation_contract import (
        BoundedMetricDimensions,
    )

    correlation_map = owner.project(
        raw_values={
            "correlation_id": CORRELATION_ID,
            "subject_id": SUBJECT_ID,
            "project_id": PROJECT_ID,
            "session_id": SESSION_ID,
            "interaction_id": None,
            "response_id": None,
            "task_id": None,
            "attempt_id": None,
            "command_id": None,
            "event_id": None,
            "outbox_id": None,
            "executor_id": None,
            "checkpoint_id": None,
            "effect_id": None,
            "presentation_id": None,
        },
        response_generation=None,
        metric_dimensions=BoundedMetricDimensions(labels=labels),
    )

    rejected = evaluate_observability_correlation_map(
        correlation_map,
        enabled=True,
        trusted_receipt_verifier=attacker.verify_receipt,
    )
    accepted = evaluate_observability_correlation_map(
        correlation_map,
        enabled=True,
        trusted_receipt_verifier=owner.verify_receipt,
    )

    assert rejected.ready is False
    assert rejected.reason is CorrelationEvaluationReason.INVALID_MAP
    assert accepted.ready is True
    assert dimensions.binding.correlation_id == CORRELATION_ID


@pytest.mark.asyncio
async def test_cross_scope_rebind_and_unbound_export_have_zero_backend_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, backend = _runtime(monkeypatch)
    await runtime.start()
    assert runtime.bind_authority(_authority())
    assert (
        runtime.bind_authority(
            _authority(subject_id="principal-foreign", project_id="project-foreign")
        )
        is False
    )
    assert runtime.health().authority_bindings == 0
    assert runtime.health().blocked_correlations == 1
    # Once contradictory owners present the same correlation, neither the old
    # nor a later claimant may be attributed through the retained old scope.
    assert runtime.bind_authority(_authority()) is False
    with pytest.raises(ProductObservabilityRuntimeError):
        await runtime.export(_observation("old-scope-after-conflict"))
    with pytest.raises(ProductObservabilityRuntimeError):
        await runtime.export(
            _observation("foreign-unbound", correlation_id="correlation-unbound")
        )

    assert backend.records() == ()
    assert backend.health().accepted == 0
    assert runtime.health().rejected_authority == 2
    assert runtime.health().rejected_correlation == 2
    await runtime.close()


@pytest.mark.asyncio
async def test_authority_capacity_never_evicts_or_allows_foreign_reuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, backend = _runtime(monkeypatch)
    runtime._binding_capacity = 1
    await runtime.start()
    assert runtime.bind_authority(_authority()) is True
    assert (
        runtime.bind_authority(_authority(correlation_id="capacity-correlation"))
        is False
    )
    assert runtime.health().authority_bindings == 1

    # A foreign claimant poisons the retained exact correlation; neither the
    # original nor foreign late fact may be projected through a remembered or
    # rebound scope.
    assert (
        runtime.bind_authority(
            _authority(subject_id="principal-foreign", project_id="project-foreign")
        )
        is False
    )
    assert runtime.bind_authority(_authority()) is False
    with pytest.raises(ProductObservabilityRuntimeError):
        await runtime.export(_observation("late-original"))
    with pytest.raises(ProductObservabilityRuntimeError):
        await runtime.export(_observation("late-foreign"))

    assert backend.records() == ()
    assert runtime.health().authority_bindings == 0
    assert runtime.health().blocked_correlations == 1
    await runtime.close()


@pytest.mark.asyncio
async def test_diagnostic_capacity_preserves_explicit_identity_before_worker_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, backend = _runtime(monkeypatch)
    runtime._binding_capacity = 1
    await runtime.start()
    assert runtime.bind_authority(_authority()) is True
    first = _observation("explicit-first")
    second_payload = _observation("explicit-second").to_dict()
    second_payload["source_component"] = "product.composition.registry"
    second = create_observation(second_payload)
    identity = ProductDiagnosticIdentity(
        seam=ProductDiagnosticSeam.COMMAND,
        seam_id="exact-command",
        command_id="command-1",
    )
    assert runtime.register_diagnostic_identity(
        first.event_id,
        identity,
        correlation_id=CORRELATION_ID,
    )
    assert (
        runtime.register_diagnostic_identity(
            second.event_id,
            replace(identity, seam_id="second-command", command_id="command-2"),
            correlation_id=CORRELATION_ID,
        )
        is False
    )

    # A Registry-owned exact seam cannot silently fall back to inference after
    # registration saturation, while the already accepted identity remains.
    with pytest.raises(ProductObservabilityRuntimeError):
        await runtime.export(second)
    await runtime.export(first)
    assert len(backend.records()) == 1
    assert backend.records()[0].seam is ProductDiagnosticSeam.COMMAND
    await runtime.close()


@pytest.mark.asyncio
async def test_private_or_forged_fact_and_backend_capacity_fail_without_business_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, backend = _runtime(monkeypatch, backend_capacity=1)
    await runtime.start()
    assert runtime.bind_authority(_authority())
    forged = _observation("forged-private")
    object.__setattr__(forged, "source_component", "https://private.example")
    with pytest.raises(ProductObservabilityRuntimeError):
        await runtime.export(forged)
    await runtime.export(_observation("capacity-first"))
    assert backend.health().accepted == 1
    assert backend.health().ready is False
    assert runtime.health().ready is False
    with pytest.raises(ProductObservabilityRuntimeError):
        await runtime.export(_observation("capacity-second"))

    assert len(backend.records()) == 1
    assert runtime.health().rejected_private == 1
    assert runtime.health().rejected_backend == 1
    assert backend.health().state is ProductObservabilityRuntimeState.FAILED
    assert backend.health().ready is False
    assert runtime.health().ready is False
    assert all(
        value is False
        for value in (
            False,  # Agent
            False,  # Tool
            False,  # Task
            False,  # audio
            False,  # history
            False,  # persistence
        )
    )
    await runtime.close()
    with pytest.raises(ProductObservabilityRuntimeError):
        await runtime.start()


def test_runtime_rejects_a_forged_or_downgraded_declaration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, _ = _runtime(monkeypatch)
    declaration = runtime._declaration
    forged = replace(declaration)
    object.__setattr__(forged, "authorization_granted", True)

    with pytest.raises(ProductObservabilityRuntimeError):
        ProductObservabilityRuntime(
            declaration=forged,
            projection_owner=TrustedCorrelationProjectionOwner(b"z" * 32),
            backend=BoundedInMemoryOtelBackend(),
        )
