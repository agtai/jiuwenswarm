# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Validated product composition for the Live Voice OTel backend boundary.

The runtime is a diagnostic consumer only.  Authenticated product authority is
projected into a bounded, process-local lookup, high-cardinality identities are
tokenized by one injected keyed owner, and only canonical P3-8A OTel records
plus public correlation tokens can cross the backend callback boundary.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock
from types import MappingProxyType
from typing import Final

from jiuwenswarm.server.live_voice.live_voice_configuration_declaration import (
    AuthenticationMode,
    LiveVoiceCapability,
    LiveVoiceCapabilityDeclaration,
    LiveVoiceDeploymentProfile,
    ProviderCapability,
    ValidatedLiveVoiceConfiguration,
    ValidatedProviderConfiguration,
    declare_live_voice_capabilities,
)
from jiuwenswarm.server.live_voice.observability import (
    LiveVoiceMetric,
    LiveVoiceObservation,
    contains_private_observability_content,
    create_metric,
    create_observation,
)
from jiuwenswarm.server.live_voice.observability_correlation_contract import (
    CORRELATION_TOKENIZATION_RECEIPT_VERSION,
    OBSERVABILITY_CORRELATION_CONTRACT_VERSION,
    BoundedMetricDimensions,
    CorrelationCausationLink,
    CorrelationIdentityKind,
    CorrelationTokenizationIssuer,
    CorrelationTokenizationMethod,
    CorrelationTokenizationReceipt,
    MetricDimension,
    MetricDimensionKey,
    ObservabilityCorrelationMap,
    evaluate_observability_correlation_map,
)
from jiuwenswarm.server.live_voice.observability_exporter import ExportRecord
from jiuwenswarm.server.live_voice.observability_otel_codec import (
    OtelBackendRecord,
    OtelBackendSignalKind,
    OtelTraceContext,
    encode_metric_for_otel_backend,
    encode_observation_for_otel_backend,
    validate_otel_backend_record,
)
from jiuwenswarm.server.live_voice.product_authority import ResolvedProductAuthority


PRODUCT_OBSERVABILITY_ENABLE_ENV: Final = (
    "JIUWENSWARM_LIVE_VOICE_PRODUCT_OBSERVABILITY_ENABLED"
)
PRODUCT_OBSERVABILITY_BACKEND_ENV: Final = (
    "JIUWENSWARM_LIVE_VOICE_PRODUCT_OBSERVABILITY_BACKEND"
)
PRODUCT_OBSERVABILITY_TOKEN_KEY_ENV: Final = (
    "JIUWENSWARM_LIVE_VOICE_PRODUCT_OBSERVABILITY_TOKEN_KEY_HEX"
)
PRODUCT_OBSERVABILITY_BACKEND_ID: Final = "otel_memory_v1"
PRODUCT_OBSERVABILITY_RUNTIME_VERSION: Final = (
    "live-voice.product-observability-runtime.v1"
)
_TOKEN_FIELDS: Final = (
    "map_id",
    "correlation_id",
    "subject_id",
    "project_id",
    "session_id",
    "interaction_id",
    "response_id",
    "task_id",
    "attempt_id",
    "command_id",
    "event_id",
    "outbox_id",
    "executor_id",
    "checkpoint_id",
    "effect_id",
    "presentation_id",
)
_IDENTITY_KIND_BY_FIELD: Final = MappingProxyType(
    {
        "subject_id": CorrelationIdentityKind.SUBJECT,
        "project_id": CorrelationIdentityKind.PROJECT,
        "session_id": CorrelationIdentityKind.SESSION,
        "interaction_id": CorrelationIdentityKind.INTERACTION,
        "response_id": CorrelationIdentityKind.RESPONSE,
        "task_id": CorrelationIdentityKind.TASK,
        "attempt_id": CorrelationIdentityKind.ATTEMPT,
        "command_id": CorrelationIdentityKind.COMMAND,
        "event_id": CorrelationIdentityKind.EVENT,
        "outbox_id": CorrelationIdentityKind.OUTBOX,
        "executor_id": CorrelationIdentityKind.EXECUTOR,
        "checkpoint_id": CorrelationIdentityKind.CHECKPOINT,
        "effect_id": CorrelationIdentityKind.EFFECT,
        "presentation_id": CorrelationIdentityKind.PRESENTATION,
    }
)


class ProductObservabilityRuntimeError(RuntimeError):
    """Raised when selected diagnostic dependencies cannot become ready."""


class ProductObservabilityRuntimeState(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    CLOSING = "closing"
    CLOSED = "closed"
    FAILED = "failed"


class ProductDiagnosticSeam(StrEnum):
    ADMISSION = "admission"
    QUEUE = "queue"
    LEASE = "lease"
    COMMAND = "command"
    EVENT = "event"
    OUTBOX = "outbox"
    EXECUTOR = "executor"
    CHECKPOINT = "checkpoint"
    EFFECT = "effect"
    RESULT = "result"
    RESPONSE = "response"
    PRESENTATION = "presentation"
    GENERATION = "generation"
    ACK = "ack"


@dataclass(frozen=True, slots=True)
class ProductDiagnosticIdentity:
    """Optional authority-read identities for one exact diagnostic seam."""

    seam: ProductDiagnosticSeam
    seam_id: str
    command_id: str | None = None
    event_id: str | None = None
    outbox_id: str | None = None
    executor_id: str | None = None
    checkpoint_id: str | None = None
    effect_id: str | None = None
    presentation_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.seam) is not ProductDiagnosticSeam:
            raise ValueError("diagnostic seam must use the closed vocabulary")
        for field_name in (
            "seam_id",
            "command_id",
            "event_id",
            "outbox_id",
            "executor_id",
            "checkpoint_id",
            "effect_id",
            "presentation_id",
        ):
            value = getattr(self, field_name)
            if value is not None and (
                type(value) is not str or not value or len(value) > 256
            ):
                raise ValueError("diagnostic identity is outside the bounded range")


@dataclass(frozen=True, slots=True)
class ProductOtelBackendRecord:
    """Re-canonicalized backend record with identities confined to span trace."""

    signal_kind: OtelBackendSignalKind
    canonical_bytes: bytes
    payload_sha256: str

    def __post_init__(self) -> None:
        if type(self.signal_kind) is not OtelBackendSignalKind:
            raise ValueError("backend signal kind is invalid")
        if type(self.canonical_bytes) is not bytes or not self.canonical_bytes:
            raise ValueError("backend payload must be immutable bytes")
        if (
            type(self.payload_sha256) is not str
            or self.payload_sha256 != hashlib.sha256(self.canonical_bytes).hexdigest()
        ):
            raise ValueError("backend payload digest does not match")
        try:
            payload = json.loads(self.canonical_bytes.decode("ascii"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("backend payload is not canonical ASCII JSON") from exc
        if type(payload) is not dict or self.canonical_bytes != _canonical_bytes(
            payload
        ):
            raise ValueError("backend payload is not canonical")
        common = {
            "schema_version",
            "signal_kind",
            "name",
            "observed_at",
            "attributes",
        }
        expected = (
            common | {"trace"}
            if self.signal_kind is OtelBackendSignalKind.SPAN_EVENT
            else common | {"metric"}
        )
        if set(payload) != expected:
            raise ValueError("backend payload has an invalid closed shape")
        if (
            payload["schema_version"] != PRODUCT_OBSERVABILITY_RUNTIME_VERSION
            or payload["signal_kind"] != self.signal_kind.value
            or type(payload["name"]) is not str
            or not payload["name"]
            or type(payload["observed_at"]) is not str
        ):
            raise ValueError("backend payload metadata is invalid")
        attributes = payload["attributes"]
        if type(attributes) is not dict or any(
            key not in {item.value for item in MetricDimensionKey} for key in attributes
        ):
            raise ValueError("backend attributes exceed closed metric dimensions")
        BoundedMetricDimensions(
            labels=tuple(
                sorted(
                    (
                        MetricDimension(key=MetricDimensionKey(key), value=value)
                        for key, value in attributes.items()
                    ),
                    key=lambda item: item.key.value,
                )
            )
        )
        if self.signal_kind is OtelBackendSignalKind.SPAN_EVENT:
            trace = payload["trace"]
            if type(trace) is not dict or set(trace) != {
                "trace_id",
                "span_id",
                "parent_span_id",
                "identities",
                "causation",
            }:
                raise ValueError("backend trace has an invalid closed shape")
            identities = trace["identities"]
            if type(identities) is not dict or not identities:
                raise ValueError("span trace identities are required")
            allowed_identity_fields = set(_TOKEN_FIELDS) | {
                "tokenization_receipt_id",
                "response_generation",
                "seam_id",
            }
            if (
                not {
                    "map_id",
                    "tokenization_receipt_id",
                    "correlation_id",
                    "subject_id",
                    "project_id",
                    "session_id",
                    "seam_id",
                }.issubset(identities)
                or set(identities) - allowed_identity_fields
            ):
                raise ValueError("span trace identities exceed the closed shape")
            if any(
                type(key) is not str
                or type(value) not in {str, int}
                or (type(value) is int and (key != "response_generation" or value < 0))
                or (type(value) is str and not value.startswith("lvpub:"))
                for key, value in identities.items()
            ):
                raise ValueError("span trace identity is not public")
            OtelTraceContext(
                trace_id=trace["trace_id"],
                span_id=trace["span_id"],
                parent_span_id=trace["parent_span_id"],
                correlation_id=identities["correlation_id"],
            )
            causation = trace["causation"]
            if type(causation) is not list or not causation:
                raise ValueError("span causation is required")
            canonical_causation = sorted(
                causation,
                key=lambda item: (
                    item.get("cause_kind", ""),
                    item.get("effect_kind", ""),
                    item.get("cause_id", ""),
                    item.get("effect_id", ""),
                ),
            )
            if causation != canonical_causation:
                raise ValueError("span causation must be canonical")
            causation_kinds: set[
                tuple[CorrelationIdentityKind, CorrelationIdentityKind]
            ] = set()
            for link in causation:
                if type(link) is not dict or set(link) != {
                    "cause_kind",
                    "cause_id",
                    "effect_kind",
                    "effect_id",
                }:
                    raise ValueError("span causation link is invalid")
                try:
                    validated_link = CorrelationCausationLink(
                        cause_kind=CorrelationIdentityKind(link["cause_kind"]),
                        cause_id=link["cause_id"],
                        effect_kind=CorrelationIdentityKind(link["effect_kind"]),
                        effect_id=link["effect_id"],
                    )
                except (TypeError, ValueError) as exc:
                    raise ValueError("span causation link is invalid") from exc
                cause_field = f"{validated_link.cause_kind.value}_id"
                effect_field = f"{validated_link.effect_kind.value}_id"
                if (
                    identities.get(cause_field) != validated_link.cause_id
                    or identities.get(effect_field) != validated_link.effect_id
                ):
                    raise ValueError("span causation does not bind trace identities")
                causation_kinds.add(
                    (validated_link.cause_kind, validated_link.effect_kind)
                )
            if not {
                (CorrelationIdentityKind.SUBJECT, CorrelationIdentityKind.PROJECT),
                (CorrelationIdentityKind.PROJECT, CorrelationIdentityKind.SESSION),
            }.issubset(causation_kinds):
                raise ValueError("span causation is missing the root authority chain")
        elif "trace" in payload or any(
            key.endswith("_id") or "identity" in key for key in attributes
        ):
            raise ValueError("metrics cannot carry high-cardinality identities")
        if contains_private_observability_content(payload):
            raise ValueError("backend payload contains private content")


@dataclass(frozen=True, slots=True)
class ProductOtelBackendEnvelope:
    """The only content allowed to cross the selected backend seam."""

    runtime_version: str
    backend_id: str
    seam: ProductDiagnosticSeam
    record: ProductOtelBackendRecord
    trace_identities: tuple[tuple[str, str | int], ...]
    metric_dimensions: BoundedMetricDimensions

    def __post_init__(self) -> None:
        if self.runtime_version != PRODUCT_OBSERVABILITY_RUNTIME_VERSION:
            raise ValueError("unsupported product observability runtime")
        if self.backend_id != PRODUCT_OBSERVABILITY_BACKEND_ID:
            raise ValueError("backend envelope does not match selected backend")
        if type(self.seam) is not ProductDiagnosticSeam:
            raise ValueError("backend seam must use the closed vocabulary")
        if type(self.record) is not ProductOtelBackendRecord:
            raise ValueError("backend envelope requires a canonical product record")
        if (
            type(self.trace_identities) is not tuple
            or self.trace_identities != tuple(sorted(self.trace_identities))
            or len({key for key, _ in self.trace_identities})
            != len(self.trace_identities)
        ):
            raise ValueError("trace identities must be one closed canonical tuple")
        if any(
            type(key) is not str or type(value) not in {str, int}
            for key, value in self.trace_identities
        ):
            raise ValueError("trace identities contain an invalid value")
        if type(self.metric_dimensions) is not BoundedMetricDimensions:
            raise ValueError("metric dimensions require the bounded contract")
        if self.record.signal_kind is OtelBackendSignalKind.SPAN_EVENT:
            if not self.trace_identities:
                raise ValueError("span envelopes require trace-only identities")
        elif self.trace_identities:
            raise ValueError("metric envelopes cannot carry trace identities")
        payload = json.loads(self.record.canonical_bytes.decode("ascii"))
        if payload["attributes"] != self.metric_dimensions.to_dict():
            raise ValueError("backend dimensions do not match the canonical record")
        if self.record.signal_kind is OtelBackendSignalKind.SPAN_EVENT and (
            payload["trace"]["identities"] != dict(self.trace_identities)
        ):
            raise ValueError("backend trace identities do not match the envelope")
        if contains_private_observability_content(
            {
                "trace": dict(self.trace_identities),
                "metric": self.metric_dimensions.to_dict(),
            }
        ):
            raise ValueError("backend envelope contains private content")


@dataclass(frozen=True, slots=True)
class ProductObservabilityBackendHealth:
    backend_id: str
    state: ProductObservabilityRuntimeState
    ready: bool
    accepted: int
    rejected: int
    retained: int


class BoundedInMemoryOtelBackend:
    """Bounded callback backend used by the current local product profile."""

    def __init__(self, *, capacity: int = 256) -> None:
        if type(capacity) is not int or capacity <= 0:
            raise ValueError("backend capacity must be a positive integer")
        self._capacity = capacity
        self._state = ProductObservabilityRuntimeState.CREATED
        self._records: list[ProductOtelBackendEnvelope] = []
        self._accepted = 0
        self._rejected = 0
        self._lock = Lock()

    async def start(self) -> ProductObservabilityBackendHealth:
        with self._lock:
            if self._state is ProductObservabilityRuntimeState.CREATED:
                self._state = ProductObservabilityRuntimeState.RUNNING
            elif self._state is not ProductObservabilityRuntimeState.RUNNING:
                raise ProductObservabilityRuntimeError("backend cannot restart")
            return self._health_locked()

    async def emit(self, envelope: ProductOtelBackendEnvelope) -> None:
        if type(envelope) is not ProductOtelBackendEnvelope:
            with self._lock:
                self._rejected += 1
            raise ProductObservabilityRuntimeError(
                "backend rejected an invalid envelope"
            )
        with self._lock:
            if self._state is not ProductObservabilityRuntimeState.RUNNING:
                self._rejected += 1
                raise ProductObservabilityRuntimeError("backend is not running")
            if len(self._records) >= self._capacity:
                self._rejected += 1
                # This bounded in-process sink cannot accept another record and
                # has no drain operation. Preserve that truth in health instead
                # of advertising readiness after a rejected backend effect.
                self._state = ProductObservabilityRuntimeState.FAILED
                raise ProductObservabilityRuntimeError("backend capacity is full")
            self._records.append(envelope)
            self._accepted += 1

    async def close(self) -> ProductObservabilityBackendHealth:
        with self._lock:
            if self._state in {
                ProductObservabilityRuntimeState.CREATED,
                ProductObservabilityRuntimeState.RUNNING,
                ProductObservabilityRuntimeState.FAILED,
            }:
                self._state = ProductObservabilityRuntimeState.CLOSED
            return self._health_locked()

    def health(self) -> ProductObservabilityBackendHealth:
        with self._lock:
            return self._health_locked()

    def records(self) -> tuple[ProductOtelBackendEnvelope, ...]:
        with self._lock:
            return tuple(self._records)

    def validated_provider_configuration(self) -> ValidatedProviderConfiguration:
        """Project only construction facts owned by this exact backend."""

        projection = {
            "backend_id": PRODUCT_OBSERVABILITY_BACKEND_ID,
            "implementation": f"{type(self).__module__}.{type(self).__qualname__}",
            "capacity": self._capacity,
            "transport": "in_process_callback",
            "persistence": False,
        }
        digest = hashlib.sha256(_canonical_bytes(projection)).hexdigest()
        return ValidatedProviderConfiguration(
            provider_id=PRODUCT_OBSERVABILITY_BACKEND_ID,
            capabilities=(ProviderCapability.TELEMETRY_EXPORT,),
            validation_receipt_id=f"otel-memory.v1.{digest[:32]}",
            configuration_digest=digest,
        )

    def _health_locked(self) -> ProductObservabilityBackendHealth:
        return ProductObservabilityBackendHealth(
            backend_id=PRODUCT_OBSERVABILITY_BACKEND_ID,
            state=self._state,
            ready=(
                self._state is ProductObservabilityRuntimeState.RUNNING
                and len(self._records) < self._capacity
            ),
            accepted=self._accepted,
            rejected=self._rejected,
            retained=len(self._records),
        )


class TrustedCorrelationProjectionOwner:
    """Keyed identity owner and the independent receipt-verifier trust seam."""

    def __init__(self, key: bytes) -> None:
        if type(key) is not bytes or len(key) < 32:
            raise ValueError("correlation projection key is invalid")
        self._key = key

    def _mac(self, purpose: str, value: str) -> str:
        return hmac.new(
            self._key,
            f"{purpose}\0{value}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _scope_tag(self, subject_id: str, project_id: str, session_id: str) -> str:
        return self._mac("scope", f"{subject_id}\0{project_id}\0{session_id}")[:16]

    def _token(self, kind: str, scope_tag: str, raw_identity: str) -> str:
        digest = self._mac(f"token:{kind}:{scope_tag}", raw_identity)
        return f"lvpub:{kind}:v1:{scope_tag}:{digest}"

    @staticmethod
    def _token_set_digest(values: Mapping[str, str | None]) -> str:
        encoded = "\n".join(
            f"{field_name}={values[field_name]}"
            for field_name in _TOKEN_FIELDS
            if values.get(field_name) is not None
        ).encode("ascii")
        return hashlib.sha256(encoded).hexdigest()

    def project(
        self,
        *,
        raw_values: Mapping[str, str | None],
        response_generation: int | None,
        metric_dimensions: BoundedMetricDimensions,
    ) -> ObservabilityCorrelationMap:
        for required in ("subject_id", "project_id", "session_id", "correlation_id"):
            value = raw_values.get(required)
            if type(value) is not str or not value or len(value) > 256:
                raise ProductObservabilityRuntimeError(
                    "authority identity is unavailable"
                )
        subject_id = str(raw_values["subject_id"])
        project_id = str(raw_values["project_id"])
        session_id = str(raw_values["session_id"])
        scope_tag = self._scope_tag(subject_id, project_id, session_id)
        tokens: dict[str, str | None] = {}
        map_source = "\0".join(
            str(raw_values.get(field_name) or "") for field_name in _TOKEN_FIELDS[1:]
        )
        tokens["map_id"] = self._token("map", scope_tag, map_source)
        tokens["correlation_id"] = self._token(
            "correlation", scope_tag, str(raw_values["correlation_id"])
        )
        for field_name in _TOKEN_FIELDS[2:]:
            raw = raw_values.get(field_name)
            kind = _IDENTITY_KIND_BY_FIELD[field_name].value
            tokens[field_name] = (
                None if raw is None else self._token(kind, scope_tag, raw)
            )
        token_digest = self._token_set_digest(tokens)
        receipt_id = self._token("receipt", scope_tag, token_digest)
        receipt = CorrelationTokenizationReceipt(
            contract_version=CORRELATION_TOKENIZATION_RECEIPT_VERSION,
            receipt_id=receipt_id,
            issuer=CorrelationTokenizationIssuer.IDENTITY_PROJECTION_OWNER,
            method=CorrelationTokenizationMethod.HMAC_SHA256,
            scope_tag=scope_tag,
            token_set_digest=token_digest,
            raw_identity_included=False,
        )
        causation = self._causation(tokens)
        candidate = ObservabilityCorrelationMap(
            contract_version=OBSERVABILITY_CORRELATION_CONTRACT_VERSION,
            map_id=str(tokens["map_id"]),
            correlation_id=str(tokens["correlation_id"]),
            subject_id=str(tokens["subject_id"]),
            project_id=str(tokens["project_id"]),
            session_id=str(tokens["session_id"]),
            tokenization_receipt=receipt,
            metric_dimensions=metric_dimensions,
            interaction_id=tokens["interaction_id"],
            response_id=tokens["response_id"],
            response_generation=response_generation,
            task_id=tokens["task_id"],
            attempt_id=tokens["attempt_id"],
            command_id=tokens["command_id"],
            event_id=tokens["event_id"],
            outbox_id=tokens["outbox_id"],
            executor_id=tokens["executor_id"],
            checkpoint_id=tokens["checkpoint_id"],
            effect_id=tokens["effect_id"],
            presentation_id=tokens["presentation_id"],
            causation=causation,
        )
        evaluated = evaluate_observability_correlation_map(
            candidate,
            enabled=True,
            trusted_receipt_verifier=self.verify_receipt,
        )
        if not evaluated.ready or evaluated.correlation_map is None:
            raise ProductObservabilityRuntimeError("correlation map failed closed")
        return evaluated.correlation_map

    def verify_receipt(
        self,
        receipt: CorrelationTokenizationReceipt,
        token_values: Mapping[str, str | None],
    ) -> bool:
        try:
            expected_digest = self._token_set_digest(token_values)
            expected_receipt = self._token(
                "receipt", receipt.scope_tag, expected_digest
            )
        except Exception:
            return False
        return receipt.token_set_digest == expected_digest and hmac.compare_digest(
            receipt.receipt_id, expected_receipt
        )

    @staticmethod
    def _causation(
        values: Mapping[str, str | None],
    ) -> tuple[CorrelationCausationLink, ...]:
        edges: list[tuple[CorrelationIdentityKind, CorrelationIdentityKind]] = [
            (CorrelationIdentityKind.SUBJECT, CorrelationIdentityKind.PROJECT),
            (CorrelationIdentityKind.PROJECT, CorrelationIdentityKind.SESSION),
        ]
        for cause, effect in (
            (CorrelationIdentityKind.SESSION, CorrelationIdentityKind.INTERACTION),
            (CorrelationIdentityKind.SESSION, CorrelationIdentityKind.TASK),
            (CorrelationIdentityKind.INTERACTION, CorrelationIdentityKind.RESPONSE),
            (CorrelationIdentityKind.TASK, CorrelationIdentityKind.ATTEMPT),
            (CorrelationIdentityKind.TASK, CorrelationIdentityKind.COMMAND),
            (CorrelationIdentityKind.TASK, CorrelationIdentityKind.EVENT),
            (CorrelationIdentityKind.COMMAND, CorrelationIdentityKind.EVENT),
            (CorrelationIdentityKind.COMMAND, CorrelationIdentityKind.OUTBOX),
            (CorrelationIdentityKind.ATTEMPT, CorrelationIdentityKind.OUTBOX),
            (CorrelationIdentityKind.ATTEMPT, CorrelationIdentityKind.EXECUTOR),
            (CorrelationIdentityKind.OUTBOX, CorrelationIdentityKind.EXECUTOR),
            (CorrelationIdentityKind.EXECUTOR, CorrelationIdentityKind.CHECKPOINT),
            (CorrelationIdentityKind.EXECUTOR, CorrelationIdentityKind.EFFECT),
            (CorrelationIdentityKind.RESPONSE, CorrelationIdentityKind.PRESENTATION),
            (CorrelationIdentityKind.EVENT, CorrelationIdentityKind.PRESENTATION),
        ):
            cause_field = f"{cause.value}_id"
            effect_field = f"{effect.value}_id"
            if (
                values.get(cause_field) is not None
                and values.get(effect_field) is not None
            ):
                edges.append((cause, effect))
        links = tuple(
            CorrelationCausationLink(
                cause_kind=cause,
                cause_id=str(values[f"{cause.value}_id"]),
                effect_kind=effect,
                effect_id=str(values[f"{effect.value}_id"]),
            )
            for cause, effect in edges
        )
        return tuple(sorted(links, key=lambda item: item.sort_key()))

    def public_aux_token(self, kind: str, scope_tag: str, raw_identity: str) -> str:
        if type(kind) is not str or not kind.replace("_", "").islower():
            raise ValueError("auxiliary identity kind is invalid")
        return self._token(kind, scope_tag, raw_identity)


@dataclass(frozen=True, slots=True)
class _AuthorityBinding:
    subject_id: str
    project_id: str
    session_id: str
    correlation_id: str


@dataclass(frozen=True, slots=True)
class ProductObservabilityRuntimeHealth:
    state: ProductObservabilityRuntimeState
    ready: bool
    configuration_id: str
    backend: ProductObservabilityBackendHealth
    authority_bindings: int
    blocked_correlations: int
    authority_globally_blocked: bool
    diagnostic_identities: int
    delivered_records: int
    idempotent_replays: int
    rejected_replays: int
    rejected_authority: int
    rejected_correlation: int
    rejected_private: int
    rejected_codec: int
    rejected_backend: int


class ProductObservabilityRuntime:
    """Lifecycle owner for configuration, correlation, codec and backend.

    This callback deliberately owns no queue or worker.  The accepted product
    adapter/exporter owns the one bounded FIFO and calls :meth:`export` for its
    single retained attempt.  Keeping the backend callback synchronous at this
    boundary preserves one backpressure and close authority.
    """

    def __init__(
        self,
        *,
        declaration: LiveVoiceCapabilityDeclaration,
        projection_owner: TrustedCorrelationProjectionOwner,
        backend: BoundedInMemoryOtelBackend,
    ) -> None:
        checked = _validated_runtime_declaration(declaration)
        if type(projection_owner) is not TrustedCorrelationProjectionOwner:
            raise ProductObservabilityRuntimeError(
                "trusted projection owner is required"
            )
        if type(backend) is not BoundedInMemoryOtelBackend:
            raise ProductObservabilityRuntimeError("selected backend is unavailable")
        self._declaration = checked
        self._projection_owner = projection_owner
        self._backend = backend
        self._state = ProductObservabilityRuntimeState.CREATED
        self._authority: OrderedDict[str, _AuthorityBinding] = OrderedDict()
        self._blocked_correlations: set[str] = set()
        self._authority_globally_blocked = False
        self._diagnostic: OrderedDict[tuple[str, str], ProductDiagnosticIdentity] = (
            OrderedDict()
        )
        self._delivered: OrderedDict[tuple[str, str, str], str] = OrderedDict()
        self._binding_capacity = 256
        self._lock = Lock()
        self._rejected_authority = 0
        self._rejected_correlation = 0
        self._rejected_private = 0
        self._rejected_codec = 0
        self._rejected_backend = 0
        self._idempotent_replays = 0
        self._rejected_replays = 0

    async def start(self) -> ProductObservabilityRuntimeHealth:
        if self._state is ProductObservabilityRuntimeState.RUNNING:
            return self.health()
        if self._state is not ProductObservabilityRuntimeState.CREATED:
            raise ProductObservabilityRuntimeError(
                "observability runtime cannot restart"
            )
        try:
            backend = await self._backend.start()
        except Exception:
            self._state = ProductObservabilityRuntimeState.FAILED
            raise
        if backend.ready is not True:
            self._state = ProductObservabilityRuntimeState.FAILED
            raise ProductObservabilityRuntimeError("selected backend failed readiness")
        self._state = ProductObservabilityRuntimeState.RUNNING
        return self.health()

    def bind_authority(self, authority: object) -> bool:
        if type(authority) is not ResolvedProductAuthority:
            with self._lock:
                self._rejected_authority += 1
            return False
        scope = authority.scope
        project_id = authority.project_id
        if (
            project_id is None
            or scope.subject_id != authority.principal_id
            or scope.project_id != project_id
            or scope.session_id != authority.session_id
            or authority.correlation_id == ""
        ):
            with self._lock:
                self._rejected_authority += 1
            return False
        binding = _AuthorityBinding(
            subject_id=authority.principal_id,
            project_id=project_id,
            session_id=authority.session_id,
            correlation_id=authority.correlation_id,
        )
        with self._lock:
            if self._state is not ProductObservabilityRuntimeState.RUNNING:
                self._rejected_authority += 1
                return False
            if (
                self._authority_globally_blocked
                or binding.correlation_id in self._blocked_correlations
            ):
                self._rejected_authority += 1
                return False
            existing = self._authority.get(binding.correlation_id)
            if existing is not None and existing != binding:
                self._authority.pop(binding.correlation_id, None)
                if len(self._blocked_correlations) >= self._binding_capacity:
                    # A bounded process cannot retain an unbounded poison list.
                    # Saturation therefore closes all future correlation use
                    # instead of evicting an old conflict and risking reuse.
                    self._authority_globally_blocked = True
                    self._authority.clear()
                else:
                    self._blocked_correlations.add(binding.correlation_id)
                self._rejected_authority += 1
                return False
            if existing is None and len(self._authority) >= self._binding_capacity:
                # Never forget an authority binding: a late fact for an evicted
                # correlation could otherwise be attributed to a foreign scope
                # after reuse. New bindings fail closed while retained owners
                # continue to be checked exactly.
                self._rejected_authority += 1
                return False
            self._authority[binding.correlation_id] = binding
            self._authority.move_to_end(binding.correlation_id)
        return True

    def register_diagnostic_identity(
        self,
        source_record_id: str,
        identity: ProductDiagnosticIdentity,
        *,
        correlation_id: str,
    ) -> bool:
        if (
            type(source_record_id) is not str
            or not source_record_id
            or len(source_record_id) > 128
            or type(identity) is not ProductDiagnosticIdentity
            or type(correlation_id) is not str
            or not correlation_id
            or len(correlation_id) > 128
        ):
            return False
        key = (correlation_id, source_record_id)
        with self._lock:
            if self._state is not ProductObservabilityRuntimeState.RUNNING:
                return False
            existing = self._diagnostic.get(key)
            if existing is not None and existing != identity:
                return False
            if existing is None and len(self._diagnostic) >= self._binding_capacity:
                # The accepted adapter may export asynchronously. Eviction here
                # would let an already-accepted explicit identity fall back to
                # an inferred seam or be rebound before the worker runs.
                return False
            self._diagnostic[key] = identity
            self._diagnostic.move_to_end(key)
        return True

    async def export(self, record: ExportRecord) -> None:
        if self._state is not ProductObservabilityRuntimeState.RUNNING:
            raise ProductObservabilityRuntimeError("runtime backend is unavailable")
        await self._export_record(record)

    async def close(
        self, *, timeout_seconds: float | None = None
    ) -> ProductObservabilityRuntimeHealth:
        del timeout_seconds  # the accepted adapter owns the only drain deadline
        if self._state is ProductObservabilityRuntimeState.CLOSED:
            return self.health()
        self._state = ProductObservabilityRuntimeState.CLOSING
        try:
            await self._backend.close()
        except Exception:
            self._state = ProductObservabilityRuntimeState.FAILED
            raise
        with self._lock:
            self._authority.clear()
            self._blocked_correlations.clear()
            self._authority_globally_blocked = False
            self._diagnostic.clear()
            self._delivered.clear()
        self._state = ProductObservabilityRuntimeState.CLOSED
        return self.health()

    def health(self) -> ProductObservabilityRuntimeHealth:
        backend = self._backend.health()
        with self._lock:
            authority_bindings = len(self._authority)
            blocked_correlations = len(self._blocked_correlations)
            authority_globally_blocked = self._authority_globally_blocked
            diagnostic_identities = len(self._diagnostic)
            delivered_records = len(self._delivered)
            idempotent_replays = self._idempotent_replays
            rejected_replays = self._rejected_replays
            rejected = (
                self._rejected_authority,
                self._rejected_correlation,
                self._rejected_private,
                self._rejected_codec,
                self._rejected_backend,
            )
        ready = (
            self._state is ProductObservabilityRuntimeState.RUNNING and backend.ready
        )
        return ProductObservabilityRuntimeHealth(
            state=self._state,
            ready=ready,
            configuration_id=self._declaration.source_configuration_id,
            backend=backend,
            authority_bindings=authority_bindings,
            blocked_correlations=blocked_correlations,
            authority_globally_blocked=authority_globally_blocked,
            diagnostic_identities=diagnostic_identities,
            delivered_records=delivered_records,
            idempotent_replays=idempotent_replays,
            rejected_replays=rejected_replays,
            rejected_authority=rejected[0],
            rejected_correlation=rejected[1],
            rejected_private=rejected[2],
            rejected_codec=rejected[3],
            rejected_backend=rejected[4],
        )

    async def _export_record(self, source: ExportRecord) -> None:
        if type(source) not in {LiveVoiceObservation, LiveVoiceMetric}:
            self._increment("codec")
            raise ProductObservabilityRuntimeError("invalid source fact")
        try:
            if contains_private_observability_content(source.to_dict()):
                self._increment("private")
                raise ProductObservabilityRuntimeError("private source fact rejected")
        except ProductObservabilityRuntimeError:
            raise
        except Exception as exc:
            self._increment("codec")
            raise ProductObservabilityRuntimeError("invalid source fact") from exc
        raw_correlation = source.binding.correlation_id
        source_id = (
            source.event_id
            if type(source) is LiveVoiceObservation
            else source.measurement_id
        )
        with self._lock:
            authority = (
                None
                if self._authority_globally_blocked
                or raw_correlation in self._blocked_correlations
                else self._authority.get(raw_correlation)
            )
            diagnostic = self._diagnostic.get((raw_correlation, source_id))
        if authority is None:
            self._increment("correlation")
            raise ProductObservabilityRuntimeError(
                "trusted authority binding unavailable"
            )
        if diagnostic is None and _requires_explicit_diagnostic(source):
            self._increment("codec")
            raise ProductObservabilityRuntimeError(
                "explicit product diagnostic identity unavailable"
            )
        diagnostic = diagnostic or _inferred_diagnostic(source, source_id)
        dimensions = _metric_dimensions(source)
        raw_values = _raw_correlation_values(authority, source, diagnostic)
        try:
            correlation_map = self._projection_owner.project(
                raw_values=raw_values,
                response_generation=source.binding.response_generation,
                metric_dimensions=dimensions,
            )
            public_source = _public_source_fact(
                source,
                correlation_map=correlation_map,
                projection_owner=self._projection_owner,
            )
            trace = _trace_context(correlation_map, source_id)
            encoding = (
                encode_observation_for_otel_backend(
                    public_source, trace_context=trace, enabled=True
                )
                if type(public_source) is LiveVoiceObservation
                else encode_metric_for_otel_backend(public_source, enabled=True)
            )
            if encoding.record is None or not encoding.ready_for_backend:
                raise ProductObservabilityRuntimeError(
                    "OTel codec rejected source fact"
                )
            if not validate_otel_backend_record(
                encoding.record,
                source_fact=public_source,
                trace_context=(
                    trace if type(public_source) is LiveVoiceObservation else None
                ),
            ):
                raise ProductObservabilityRuntimeError("OTel record validation failed")
            scope_tag = correlation_map.tokenization_receipt.scope_tag
            seam_id = self._projection_owner.public_aux_token(
                "seam", scope_tag, diagnostic.seam_id
            )
            trace_identities = dict(correlation_map.trace_identities())
            trace_identities["seam_id"] = seam_id
            product_record = _product_backend_record(
                source=public_source,
                codec_record=encoding.record,
                trace=trace,
                trace_identities=trace_identities,
                causation=correlation_map.causation,
                metric_dimensions=dimensions,
            )
            envelope = ProductOtelBackendEnvelope(
                runtime_version=PRODUCT_OBSERVABILITY_RUNTIME_VERSION,
                backend_id=PRODUCT_OBSERVABILITY_BACKEND_ID,
                seam=diagnostic.seam,
                record=product_record,
                trace_identities=(
                    tuple(sorted(trace_identities.items()))
                    if type(public_source) is LiveVoiceObservation
                    else ()
                ),
                metric_dimensions=dimensions,
            )
        except Exception as exc:
            self._increment("codec")
            raise ProductObservabilityRuntimeError(
                "diagnostic composition failed closed"
            ) from exc
        replay_key = (raw_correlation, encoding.record.signal_kind.value, source_id)
        replay_fingerprint = product_record.payload_sha256
        with self._lock:
            prior_fingerprint = self._delivered.get(replay_key)
            if prior_fingerprint == replay_fingerprint:
                self._delivered.move_to_end(replay_key)
                self._idempotent_replays += 1
                return
            if prior_fingerprint is not None:
                self._rejected_replays += 1
                self._rejected_codec += 1
                raise ProductObservabilityRuntimeError(
                    "diagnostic replay conflicted with the delivered record"
                )
            if len(self._delivered) >= self._binding_capacity:
                # Never evict an exact delivery identity: forgetting it could
                # turn a late replay into a duplicate backend effect.
                self._rejected_replays += 1
                self._rejected_backend += 1
                raise ProductObservabilityRuntimeError(
                    "diagnostic replay ledger capacity is exhausted"
                )
        try:
            await self._backend.emit(envelope)
        except Exception:
            self._increment("backend")
            raise
        with self._lock:
            self._delivered[replay_key] = replay_fingerprint

    def _increment(self, kind: str) -> None:
        with self._lock:
            if kind == "correlation":
                self._rejected_correlation += 1
            elif kind == "private":
                self._rejected_private += 1
            elif kind == "codec":
                self._rejected_codec += 1
            else:
                self._rejected_backend += 1


def _validated_runtime_declaration(
    declaration: object,
) -> LiveVoiceCapabilityDeclaration:
    if type(declaration) is not LiveVoiceCapabilityDeclaration:
        raise ProductObservabilityRuntimeError(
            "validated capability declaration is required"
        )
    result = declare_live_voice_capabilities(
        declaration.source_configuration,
        enabled=True,
    )
    if not result.ready or result.declaration != declaration:
        raise ProductObservabilityRuntimeError(
            "capability declaration failed validation"
        )
    expected = {
        LiveVoiceCapability.AUTHENTICATED,
        LiveVoiceCapability.FORMAL_WEB,
        LiveVoiceCapability.TASK_QUERY,
        LiveVoiceCapability.TELEMETRY_EXPORT,
    }
    if (
        declaration.profile is not LiveVoiceDeploymentProfile.FORMAL_LIVE_VOICE
        or declaration.active is not True
        or declaration.authentication_mode is not AuthenticationMode.SCOPED_BEARER
        or LiveVoiceCapability.TELEMETRY_EXPORT not in declaration.capabilities
        or set(declaration.capabilities) < expected
        or PRODUCT_OBSERVABILITY_BACKEND_ID not in declaration.provider_ids
        or declaration.authoritative is not False
        or declaration.authorization_granted is not False
    ):
        raise ProductObservabilityRuntimeError("runtime configuration is incomplete")
    provider = next(
        (
            item
            for item in declaration.source_configuration.providers
            if item.provider_id == PRODUCT_OBSERVABILITY_BACKEND_ID
        ),
        None,
    )
    if (
        provider is None
        or ProviderCapability.TELEMETRY_EXPORT not in provider.capabilities
    ):
        raise ProductObservabilityRuntimeError(
            "selected backend lacks telemetry capability"
        )
    return declaration


def _metric_dimensions(
    source: LiveVoiceObservation | LiveVoiceMetric,
) -> BoundedMetricDimensions:
    values = (
        (MetricDimensionKey.SEGMENT_NAME, source.segment_name),
        (MetricDimensionKey.IMPLEMENTATION_CLASS, source.route.implementation_class),
        (MetricDimensionKey.OUTCOME, source.outcome),
        (MetricDimensionKey.REASON_CODE, source.reason_code),
        (MetricDimensionKey.ERROR_CODE, source.error_code),
        (MetricDimensionKey.CANCEL_SCOPE, source.cancel_scope),
        (
            MetricDimensionKey.STATE,
            source.state if type(source) is LiveVoiceObservation else None,
        ),
    )
    labels = tuple(
        sorted(
            (
                MetricDimension(key=key, value=value)
                for key, value in values
                if value is not None
            ),
            key=lambda item: item.key.value,
        )
    )
    return BoundedMetricDimensions(labels=labels)


def _inferred_diagnostic(
    source: LiveVoiceObservation | LiveVoiceMetric,
    source_id: str,
) -> ProductDiagnosticIdentity:
    segment = source.segment_name
    seam = (
        ProductDiagnosticSeam.COMMAND
        if segment == "task.command"
        else ProductDiagnosticSeam.QUEUE
        if segment.endswith(".queue")
        else ProductDiagnosticSeam.PRESENTATION
        if "presentation" in segment
        else ProductDiagnosticSeam.RESPONSE
        if source.binding.response_id is not None
        else ProductDiagnosticSeam.EVENT
    )
    event_id = source.source_event_id if type(source) is LiveVoiceObservation else None
    outbox_id = (
        source.source_record_id
        if type(source) is LiveVoiceObservation and "outbox" in source.event_name
        else None
    )
    return ProductDiagnosticIdentity(
        seam=seam,
        seam_id=source_id,
        event_id=event_id,
        outbox_id=outbox_id,
    )


def _requires_explicit_diagnostic(source: ExportRecord) -> bool:
    """Identify Registry projections whose semantic identity cannot be guessed."""

    return (
        type(source) is LiveVoiceObservation
        and source.source_component == "product.composition.registry"
        and source.route.owner_module == "product.composition.registry"
    )


def _raw_correlation_values(
    authority: _AuthorityBinding,
    source: LiveVoiceObservation | LiveVoiceMetric,
    diagnostic: ProductDiagnosticIdentity,
) -> dict[str, str | None]:
    binding = source.binding
    return {
        "correlation_id": binding.correlation_id,
        "subject_id": authority.subject_id,
        "project_id": authority.project_id,
        "session_id": authority.session_id,
        "interaction_id": binding.interaction_id,
        "response_id": binding.response_id,
        "task_id": binding.task_id,
        "attempt_id": binding.attempt_id,
        "command_id": diagnostic.command_id,
        "event_id": diagnostic.event_id,
        "outbox_id": diagnostic.outbox_id,
        "executor_id": diagnostic.executor_id,
        "checkpoint_id": diagnostic.checkpoint_id,
        "effect_id": diagnostic.effect_id,
        "presentation_id": diagnostic.presentation_id,
    }


def _public_source_fact(
    source: LiveVoiceObservation | LiveVoiceMetric,
    *,
    correlation_map: ObservabilityCorrelationMap,
    projection_owner: TrustedCorrelationProjectionOwner,
) -> LiveVoiceObservation | LiveVoiceMetric:
    raw = source.to_dict()
    binding = source.binding
    scope_tag = correlation_map.tokenization_receipt.scope_tag
    projected_binding = {
        "correlation_id": correlation_map.correlation_id,
        "interaction_id": correlation_map.interaction_id,
        "turn_id": (
            None
            if binding.turn_id is None
            else projection_owner.public_aux_token("turn", scope_tag, binding.turn_id)
        ),
        "response_id": correlation_map.response_id,
        "response_generation": binding.response_generation,
        "round_id": (
            None
            if binding.round_id is None
            else projection_owner.public_aux_token("round", scope_tag, binding.round_id)
        ),
        "task_id": correlation_map.task_id,
        "attempt_id": correlation_map.attempt_id,
    }
    raw["binding"] = projected_binding
    if type(source) is LiveVoiceObservation:
        raw["event_id"] = projection_owner.public_aux_token(
            "record", scope_tag, source.event_id
        )
        if source.source_event_id is not None:
            raw["source_event_id"] = projection_owner.public_aux_token(
                "event", scope_tag, source.source_event_id
            )
        if source.source_record_id is not None:
            raw["source_record_id"] = projection_owner.public_aux_token(
                "record", scope_tag, source.source_record_id
            )
        return create_observation(raw)
    raw["measurement_id"] = projection_owner.public_aux_token(
        "measurement", scope_tag, source.measurement_id
    )
    return create_metric(raw)


def _trace_context(
    correlation_map: ObservabilityCorrelationMap,
    source_record_id: str,
) -> OtelTraceContext:
    trace_id = hashlib.sha256(
        correlation_map.correlation_id.encode("ascii")
    ).hexdigest()[:32]
    span_id = hashlib.sha256(
        f"{correlation_map.map_id}\0{source_record_id}".encode("utf-8")
    ).hexdigest()[:16]
    if set(trace_id) == {"0"}:
        trace_id = "1" + trace_id[1:]
    if set(span_id) == {"0"}:
        span_id = "1" + span_id[1:]
    return OtelTraceContext(
        trace_id=trace_id,
        span_id=span_id,
        correlation_id=correlation_map.correlation_id,
    )


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def _product_backend_record(
    *,
    source: LiveVoiceObservation | LiveVoiceMetric,
    codec_record: OtelBackendRecord,
    trace: OtelTraceContext,
    trace_identities: Mapping[str, str | int],
    causation: tuple[CorrelationCausationLink, ...],
    metric_dimensions: BoundedMetricDimensions,
) -> ProductOtelBackendRecord:
    """Map a validated P3-8A record to the stricter B1 backend projection."""

    if type(codec_record) is not OtelBackendRecord:
        raise ProductObservabilityRuntimeError("codec record is unavailable")
    decoded = json.loads(codec_record.canonical_bytes.decode("ascii"))
    if type(decoded) is not dict:
        raise ProductObservabilityRuntimeError("codec payload is invalid")
    payload: dict[str, object] = {
        "schema_version": PRODUCT_OBSERVABILITY_RUNTIME_VERSION,
        "signal_kind": codec_record.signal_kind.value,
        "name": decoded["name"],
        "observed_at": decoded["observed_at"],
        "attributes": metric_dimensions.to_dict(),
    }
    if type(source) is LiveVoiceObservation:
        payload["trace"] = {
            "trace_id": trace.trace_id,
            "span_id": trace.span_id,
            "parent_span_id": trace.parent_span_id,
            "identities": dict(sorted(trace_identities.items())),
            "causation": [
                {
                    "cause_kind": link.cause_kind.value,
                    "cause_id": link.cause_id,
                    "effect_kind": link.effect_kind.value,
                    "effect_id": link.effect_id,
                }
                for link in causation
            ],
        }
    else:
        metric = decoded.get("metric")
        if type(metric) is not dict or set(metric) != {"kind", "unit", "value"}:
            raise ProductObservabilityRuntimeError("codec metric payload is invalid")
        payload["metric"] = metric
    canonical = _canonical_bytes(payload)
    return ProductOtelBackendRecord(
        signal_kind=codec_record.signal_kind,
        canonical_bytes=canonical,
        payload_sha256=hashlib.sha256(canonical).hexdigest(),
    )


def create_product_observability_runtime_from_environment(
    *,
    backend: BoundedInMemoryOtelBackend,
    validated_configuration: object,
) -> ProductObservabilityRuntime | None:
    """Select the exact backend and trust anchor; feature-off allocates nothing."""

    enabled = str(os.getenv(PRODUCT_OBSERVABILITY_ENABLE_ENV) or "").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        return None
    backend_id = str(os.getenv(PRODUCT_OBSERVABILITY_BACKEND_ENV) or "").strip()
    if backend_id != PRODUCT_OBSERVABILITY_BACKEND_ID:
        raise ProductObservabilityRuntimeError(
            "selected observability backend is unavailable"
        )
    key_hex = str(os.getenv(PRODUCT_OBSERVABILITY_TOKEN_KEY_ENV) or "").strip()
    try:
        key = bytes.fromhex(key_hex)
    except ValueError as exc:
        raise ProductObservabilityRuntimeError(
            "correlation trust anchor is invalid"
        ) from exc
    if len(key) < 32:
        raise ProductObservabilityRuntimeError(
            "correlation trust anchor is unavailable"
        )
    if type(validated_configuration) is not ValidatedLiveVoiceConfiguration:
        raise ProductObservabilityRuntimeError(
            "owning adapters did not provide validated configuration"
        )
    selected_provider = backend.validated_provider_configuration()
    matching_providers = tuple(
        provider
        for provider in validated_configuration.providers
        if provider.provider_id == PRODUCT_OBSERVABILITY_BACKEND_ID
    )
    if matching_providers != (selected_provider,):
        raise ProductObservabilityRuntimeError(
            "validated configuration does not bind the selected backend owner"
        )
    declaration_result = declare_live_voice_capabilities(
        validated_configuration,
        enabled=True,
    )
    if not declaration_result.ready or declaration_result.declaration is None:
        raise ProductObservabilityRuntimeError(
            "owning adapter configuration failed declaration"
        )
    return ProductObservabilityRuntime(
        declaration=declaration_result.declaration,
        projection_owner=TrustedCorrelationProjectionOwner(key),
        backend=backend,
    )


def product_observability_enabled_from_environment() -> bool:
    """Read only the diagnostic master gate before allocating its dependencies."""

    return str(os.getenv(PRODUCT_OBSERVABILITY_ENABLE_ENV) or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


__all__ = [
    "BoundedInMemoryOtelBackend",
    "PRODUCT_OBSERVABILITY_BACKEND_ENV",
    "PRODUCT_OBSERVABILITY_BACKEND_ID",
    "PRODUCT_OBSERVABILITY_ENABLE_ENV",
    "PRODUCT_OBSERVABILITY_RUNTIME_VERSION",
    "PRODUCT_OBSERVABILITY_TOKEN_KEY_ENV",
    "ProductDiagnosticIdentity",
    "ProductDiagnosticSeam",
    "ProductObservabilityBackendHealth",
    "ProductObservabilityRuntime",
    "ProductObservabilityRuntimeError",
    "ProductObservabilityRuntimeHealth",
    "ProductObservabilityRuntimeState",
    "ProductOtelBackendRecord",
    "ProductOtelBackendEnvelope",
    "TrustedCorrelationProjectionOwner",
    "create_product_observability_runtime_from_environment",
    "product_observability_enabled_from_environment",
]
