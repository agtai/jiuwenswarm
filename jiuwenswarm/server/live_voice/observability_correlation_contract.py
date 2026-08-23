# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Pure, content-free correlation contracts for Live Voice diagnostics.

The records in this module describe identity and causation only. They never
collect, export, persist, schedule, or mutate product state. High-cardinality
identifiers stay in the trace correlation map; metric dimensions use a
separate closed vocabulary with bounded values.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Callable, Final, Mapping, TypeAlias

from jiuwenswarm.server.live_voice.observability import (
    CANCEL_SCOPES,
    ERROR_CODES,
    OBSERVED_STATES,
    REASON_CODES,
    ROUTE_IMPLEMENTATION_CLASSES,
    SEGMENT_NAMES,
    TERMINAL_OUTCOMES,
    contains_private_observability_content,
)


OBSERVABILITY_CORRELATION_CONTRACT_VERSION: Final = (
    "live-voice.observability-correlation.v1"
)
MAX_CORRELATION_IDENTITY_LENGTH: Final = 103
MAX_CORRELATION_LINKS: Final = 19
MAX_METRIC_DIMENSIONS: Final = 7
MAX_SAFE_GENERATION: Final = 9_007_199_254_740_991
PUBLIC_CORRELATION_TOKEN_VERSION: Final = "v1"
PUBLIC_CORRELATION_TOKEN_DIGEST_LENGTH: Final = 64
CORRELATION_TOKENIZATION_RECEIPT_VERSION: Final = (
    "live-voice.correlation-tokenization-receipt.v1"
)

_PUBLIC_TOKEN = re.compile(r"^lvpub:([a-z_]+):v1:([0-9a-f]{16}):([0-9a-f]{64})$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SCOPE_TAG = re.compile(r"^[0-9a-f]{16}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE = re.compile(r"^\+?[0-9][0-9 .()\-]{6,}$")


class CorrelationContractViolation(ValueError):
    """Raised when a correlation record could carry false or private truth."""


class PrivateCorrelationContent(CorrelationContractViolation):
    """Raised without echoing a rejected private carrier."""


class CorrelationIdentityKind(StrEnum):
    SUBJECT = "subject"
    PROJECT = "project"
    SESSION = "session"
    INTERACTION = "interaction"
    RESPONSE = "response"
    TASK = "task"
    ATTEMPT = "attempt"
    COMMAND = "command"
    EVENT = "event"
    OUTBOX = "outbox"
    EXECUTOR = "executor"
    CHECKPOINT = "checkpoint"
    EFFECT = "effect"
    PRESENTATION = "presentation"


class MetricDimensionKey(StrEnum):
    SEGMENT_NAME = "live_voice.segment_name"
    IMPLEMENTATION_CLASS = "live_voice.implementation_class"
    OUTCOME = "live_voice.outcome"
    REASON_CODE = "live_voice.reason_code"
    ERROR_CODE = "live_voice.error_code"
    CANCEL_SCOPE = "live_voice.cancel_scope"
    STATE = "live_voice.state"


class CorrelationEvaluationReason(StrEnum):
    FEATURE_DISABLED = "feature_disabled"
    READY = "ready"
    INVALID_MAP = "invalid_map"
    PRIVATE_CONTENT_REJECTED = "private_content_rejected"


class CorrelationReplayReason(StrEnum):
    FEATURE_DISABLED = "feature_disabled"
    IDEMPOTENT = "idempotent"
    INVALID_MAP = "invalid_map"
    IDENTITY_MISMATCH = "identity_mismatch"
    CONFLICT = "conflict"


class CorrelationTokenizationIssuer(StrEnum):
    IDENTITY_PROJECTION_OWNER = "identity_projection_owner"


class CorrelationTokenizationMethod(StrEnum):
    HMAC_SHA256 = "hmac_sha256"


_IDENTITY_FIELD_BY_KIND: Final[Mapping[CorrelationIdentityKind, str]] = (
    MappingProxyType(
        {
            CorrelationIdentityKind.SUBJECT: "subject_id",
            CorrelationIdentityKind.PROJECT: "project_id",
            CorrelationIdentityKind.SESSION: "session_id",
            CorrelationIdentityKind.INTERACTION: "interaction_id",
            CorrelationIdentityKind.RESPONSE: "response_id",
            CorrelationIdentityKind.TASK: "task_id",
            CorrelationIdentityKind.ATTEMPT: "attempt_id",
            CorrelationIdentityKind.COMMAND: "command_id",
            CorrelationIdentityKind.EVENT: "event_id",
            CorrelationIdentityKind.OUTBOX: "outbox_id",
            CorrelationIdentityKind.EXECUTOR: "executor_id",
            CorrelationIdentityKind.CHECKPOINT: "checkpoint_id",
            CorrelationIdentityKind.EFFECT: "effect_id",
            CorrelationIdentityKind.PRESENTATION: "presentation_id",
        }
    )
)

_PUBLIC_TOKEN_KIND_BY_FIELD: Final[Mapping[str, str]] = MappingProxyType(
    {
        "map_id": "map",
        "correlation_id": "correlation",
        **{
            field_name: kind.value
            for kind, field_name in _IDENTITY_FIELD_BY_KIND.items()
        },
    }
)

_ALLOWED_CAUSATION_EDGES: Final = frozenset(
    {
        (CorrelationIdentityKind.SUBJECT, CorrelationIdentityKind.PROJECT),
        (CorrelationIdentityKind.PROJECT, CorrelationIdentityKind.SESSION),
        (CorrelationIdentityKind.SESSION, CorrelationIdentityKind.INTERACTION),
        (CorrelationIdentityKind.SESSION, CorrelationIdentityKind.TASK),
        (CorrelationIdentityKind.INTERACTION, CorrelationIdentityKind.RESPONSE),
        (CorrelationIdentityKind.TASK, CorrelationIdentityKind.ATTEMPT),
        (CorrelationIdentityKind.TASK, CorrelationIdentityKind.COMMAND),
        (CorrelationIdentityKind.TASK, CorrelationIdentityKind.EVENT),
        (CorrelationIdentityKind.COMMAND, CorrelationIdentityKind.EVENT),
        (CorrelationIdentityKind.COMMAND, CorrelationIdentityKind.OUTBOX),
        (CorrelationIdentityKind.ATTEMPT, CorrelationIdentityKind.EVENT),
        (CorrelationIdentityKind.ATTEMPT, CorrelationIdentityKind.OUTBOX),
        (CorrelationIdentityKind.ATTEMPT, CorrelationIdentityKind.EXECUTOR),
        (CorrelationIdentityKind.OUTBOX, CorrelationIdentityKind.EXECUTOR),
        (CorrelationIdentityKind.EXECUTOR, CorrelationIdentityKind.EVENT),
        (CorrelationIdentityKind.EXECUTOR, CorrelationIdentityKind.CHECKPOINT),
        (CorrelationIdentityKind.EXECUTOR, CorrelationIdentityKind.EFFECT),
        (CorrelationIdentityKind.RESPONSE, CorrelationIdentityKind.PRESENTATION),
        (CorrelationIdentityKind.EVENT, CorrelationIdentityKind.PRESENTATION),
    }
)

_METRIC_VALUES: Final[Mapping[MetricDimensionKey, frozenset[str]]] = MappingProxyType(
    {
        MetricDimensionKey.SEGMENT_NAME: frozenset(SEGMENT_NAMES),
        MetricDimensionKey.IMPLEMENTATION_CLASS: frozenset(
            ROUTE_IMPLEMENTATION_CLASSES
        ),
        MetricDimensionKey.OUTCOME: frozenset(TERMINAL_OUTCOMES),
        MetricDimensionKey.REASON_CODE: frozenset(REASON_CODES),
        MetricDimensionKey.ERROR_CODE: frozenset(ERROR_CODES),
        MetricDimensionKey.CANCEL_SCOPE: frozenset(CANCEL_SCOPES),
        MetricDimensionKey.STATE: frozenset(OBSERVED_STATES),
    }
)

HIGH_CARDINALITY_TRACE_FIELD_ORDER: Final = (
    "map_id",
    "tokenization_receipt_id",
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
HIGH_CARDINALITY_TRACE_FIELDS: Final = frozenset(HIGH_CARDINALITY_TRACE_FIELD_ORDER)


def _looks_like_ordinary_pii(value: object) -> bool:
    return type(value) is str and (
        _EMAIL.fullmatch(value) is not None or _PHONE.fullmatch(value) is not None
    )


def _safe_public_token(
    value: object,
    field_name: str,
    token_kind: str,
    *,
    scope_tag: str | None = None,
) -> str:
    if _looks_like_ordinary_pii(value) or (
        type(value) is str and contains_private_observability_content(value)
    ):
        raise PrivateCorrelationContent(f"{field_name} contains private content")
    if type(value) is not str or len(value) > MAX_CORRELATION_IDENTITY_LENGTH:
        raise CorrelationContractViolation(
            f"{field_name} is not one bounded public token"
        )
    match = _PUBLIC_TOKEN.fullmatch(value)
    if (
        match is None
        or match.group(1) != token_kind
        or (scope_tag is not None and match.group(2) != scope_tag)
    ):
        raise CorrelationContractViolation(
            f"{field_name} is not a field-scoped public token"
        )
    return value


def _optional_public_token(
    value: object,
    field_name: str,
    token_kind: str,
    *,
    scope_tag: str,
) -> str | None:
    if value is None:
        return None
    return _safe_public_token(
        value,
        field_name,
        token_kind,
        scope_tag=scope_tag,
    )


@dataclass(frozen=True, slots=True)
class CorrelationTokenizationReceipt:
    contract_version: str
    receipt_id: str
    issuer: CorrelationTokenizationIssuer
    method: CorrelationTokenizationMethod
    scope_tag: str
    token_set_digest: str
    raw_identity_included: bool = False

    def __post_init__(self) -> None:
        if self.contract_version != CORRELATION_TOKENIZATION_RECEIPT_VERSION:
            raise CorrelationContractViolation(
                "unsupported tokenization receipt contract"
            )
        if (
            type(self.issuer) is not CorrelationTokenizationIssuer
            or self.issuer
            is not CorrelationTokenizationIssuer.IDENTITY_PROJECTION_OWNER
            or type(self.method) is not CorrelationTokenizationMethod
            or self.method is not CorrelationTokenizationMethod.HMAC_SHA256
        ):
            raise CorrelationContractViolation(
                "public tokens require the keyed identity projection owner"
            )
        if (
            type(self.scope_tag) is not str
            or _SCOPE_TAG.fullmatch(self.scope_tag) is None
        ):
            raise CorrelationContractViolation("tokenization scope tag is invalid")
        _safe_public_token(
            self.receipt_id,
            "tokenization receipt",
            "receipt",
            scope_tag=self.scope_tag,
        )
        if (
            type(self.token_set_digest) is not str
            or _DIGEST.fullmatch(self.token_set_digest) is None
        ):
            raise CorrelationContractViolation("token-set digest is invalid")
        if self.raw_identity_included is not False:
            raise PrivateCorrelationContent(
                "tokenization receipt cannot include raw identity"
            )


CorrelationTokenizationReceiptVerifier: TypeAlias = Callable[
    [CorrelationTokenizationReceipt, Mapping[str, str | None]], bool
]


@dataclass(frozen=True, slots=True)
class MetricDimension:
    key: MetricDimensionKey
    value: str

    def __post_init__(self) -> None:
        if type(self.key) is not MetricDimensionKey:
            raise CorrelationContractViolation(
                "metric dimension key must use the closed vocabulary"
            )
        if type(self.value) is not str or self.value not in _METRIC_VALUES[self.key]:
            raise CorrelationContractViolation(
                "metric dimension value must use its closed vocabulary"
            )


@dataclass(frozen=True, slots=True)
class BoundedMetricDimensions:
    labels: tuple[MetricDimension, ...]

    def __post_init__(self) -> None:
        if (
            type(self.labels) is not tuple
            or len(self.labels) > MAX_METRIC_DIMENSIONS
            or any(type(label) is not MetricDimension for label in self.labels)
        ):
            raise CorrelationContractViolation(
                "metric dimensions must be one bounded immutable tuple"
            )
        keys = tuple(label.key for label in self.labels)
        if len(keys) != len(set(keys)):
            raise CorrelationContractViolation("metric dimension keys must be unique")
        canonical = tuple(sorted(self.labels, key=lambda label: label.key.value))
        if self.labels != canonical:
            raise CorrelationContractViolation(
                "metric dimensions must use canonical key order"
            )

    def to_dict(self) -> dict[str, str]:
        return {label.key.value: label.value for label in self.labels}


@dataclass(frozen=True, slots=True)
class CorrelationCausationLink:
    cause_kind: CorrelationIdentityKind
    cause_id: str
    effect_kind: CorrelationIdentityKind
    effect_id: str

    def __post_init__(self) -> None:
        if (
            type(self.cause_kind) is not CorrelationIdentityKind
            or type(self.effect_kind) is not CorrelationIdentityKind
            or (self.cause_kind, self.effect_kind) not in _ALLOWED_CAUSATION_EDGES
        ):
            raise CorrelationContractViolation(
                "causation edge must use the closed acyclic vocabulary"
            )
        _safe_public_token(
            self.cause_id,
            "causation.cause_id",
            self.cause_kind.value,
        )
        _safe_public_token(
            self.effect_id,
            "causation.effect_id",
            self.effect_kind.value,
        )

    def sort_key(self) -> tuple[str, str, str, str]:
        return (
            self.cause_kind.value,
            self.effect_kind.value,
            self.cause_id,
            self.effect_id,
        )


def _correlation_token_set_digest(values: Mapping[str, str | None]) -> str:
    encoded = "\n".join(
        f"{field_name}={value}"
        for field_name, value in values.items()
        if value is not None
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ObservabilityCorrelationMap:
    contract_version: str
    map_id: str
    correlation_id: str
    subject_id: str
    project_id: str
    session_id: str
    tokenization_receipt: CorrelationTokenizationReceipt
    metric_dimensions: BoundedMetricDimensions
    interaction_id: str | None = None
    response_id: str | None = None
    response_generation: int | None = None
    task_id: str | None = None
    attempt_id: str | None = None
    command_id: str | None = None
    event_id: str | None = None
    outbox_id: str | None = None
    executor_id: str | None = None
    checkpoint_id: str | None = None
    effect_id: str | None = None
    presentation_id: str | None = None
    causation: tuple[CorrelationCausationLink, ...] = ()

    def __post_init__(self) -> None:
        if self.contract_version != OBSERVABILITY_CORRELATION_CONTRACT_VERSION:
            raise CorrelationContractViolation(
                "unsupported observability correlation contract"
            )
        if type(self.tokenization_receipt) is not CorrelationTokenizationReceipt:
            raise CorrelationContractViolation(
                "correlation map requires the closed tokenization receipt assertion"
            )
        receipt = CorrelationTokenizationReceipt(
            contract_version=self.tokenization_receipt.contract_version,
            receipt_id=self.tokenization_receipt.receipt_id,
            issuer=self.tokenization_receipt.issuer,
            method=self.tokenization_receipt.method,
            scope_tag=self.tokenization_receipt.scope_tag,
            token_set_digest=self.tokenization_receipt.token_set_digest,
            raw_identity_included=self.tokenization_receipt.raw_identity_included,
        )
        for field_name in (
            "map_id",
            "correlation_id",
            "subject_id",
            "project_id",
            "session_id",
        ):
            _safe_public_token(
                getattr(self, field_name),
                field_name,
                _PUBLIC_TOKEN_KIND_BY_FIELD[field_name],
                scope_tag=receipt.scope_tag,
            )
        for field_name in (
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
        ):
            _optional_public_token(
                getattr(self, field_name),
                field_name,
                _PUBLIC_TOKEN_KIND_BY_FIELD[field_name],
                scope_tag=receipt.scope_tag,
            )
        token_values = {
            field_name: getattr(self, field_name)
            for field_name in (
                "map_id",
                "correlation_id",
                *_IDENTITY_FIELD_BY_KIND.values(),
            )
        }
        if receipt.token_set_digest != _correlation_token_set_digest(token_values):
            raise CorrelationContractViolation(
                "tokenization receipt does not bind the exact public token set"
            )
        if type(self.metric_dimensions) is not BoundedMetricDimensions:
            raise CorrelationContractViolation(
                "metric dimensions require the exact bounded contract"
            )
        BoundedMetricDimensions(labels=tuple(self.metric_dimensions.labels))

        response_fields = (self.response_id, self.response_generation)
        if any(value is not None for value in response_fields):
            if self.interaction_id is None or any(
                value is None for value in response_fields
            ):
                raise CorrelationContractViolation(
                    "response identity requires interaction, response and generation"
                )
            if (
                type(self.response_generation) is not int
                or not 0 <= self.response_generation <= MAX_SAFE_GENERATION
            ):
                raise CorrelationContractViolation(
                    "response_generation must be a bounded non-negative integer"
                )
        for child, parent in (
            (self.attempt_id, self.task_id),
            (self.command_id, self.task_id),
            (self.event_id, self.task_id),
            (self.checkpoint_id, self.executor_id),
            (self.effect_id, self.executor_id),
            (self.presentation_id, self.response_id),
        ):
            if child is not None and parent is None:
                raise CorrelationContractViolation(
                    "correlation child identity is missing its exact parent"
                )
        if self.outbox_id is not None and not (self.command_id or self.attempt_id):
            raise CorrelationContractViolation(
                "outbox identity requires command or attempt causation context"
            )
        if self.executor_id is not None and not (self.attempt_id or self.outbox_id):
            raise CorrelationContractViolation(
                "executor identity requires attempt or outbox causation context"
            )
        if (
            type(self.causation) is not tuple
            or len(self.causation) > MAX_CORRELATION_LINKS
            or any(
                type(link) is not CorrelationCausationLink for link in self.causation
            )
        ):
            raise CorrelationContractViolation(
                "causation must be one bounded immutable tuple"
            )
        canonical = tuple(sorted(self.causation, key=lambda link: link.sort_key()))
        if self.causation != canonical or len(self.causation) != len(
            set(self.causation)
        ):
            raise CorrelationContractViolation(
                "causation links must be unique and canonically ordered"
            )
        for link in self.causation:
            expected_cause = getattr(self, _IDENTITY_FIELD_BY_KIND[link.cause_kind])
            expected_effect = getattr(self, _IDENTITY_FIELD_BY_KIND[link.effect_kind])
            if link.cause_id != expected_cause or link.effect_id != expected_effect:
                raise CorrelationContractViolation(
                    "causation link must bind identities from the exact map"
                )
        causation_kinds = {
            (link.cause_kind, link.effect_kind) for link in self.causation
        }
        if not {
            (CorrelationIdentityKind.SUBJECT, CorrelationIdentityKind.PROJECT),
            (CorrelationIdentityKind.PROJECT, CorrelationIdentityKind.SESSION),
        }.issubset(causation_kinds):
            raise CorrelationContractViolation(
                "subject, project and session require mandatory root causation"
            )

    def trace_identities(self) -> dict[str, str | int]:
        values: dict[str, str | int] = {
            "map_id": self.map_id,
            "tokenization_receipt_id": self.tokenization_receipt.receipt_id,
            "correlation_id": self.correlation_id,
            "subject_id": self.subject_id,
            "project_id": self.project_id,
            "session_id": self.session_id,
        }
        for field_name in HIGH_CARDINALITY_TRACE_FIELD_ORDER:
            if field_name in values:
                continue
            value = getattr(self, field_name)
            if value is not None:
                values[field_name] = value
        if self.response_generation is not None:
            values["response_generation"] = self.response_generation
        return values


@dataclass(frozen=True, slots=True)
class CorrelationEvaluation:
    ready: bool
    reason: CorrelationEvaluationReason
    correlation_map: ObservabilityCorrelationMap | None
    exporter_called: bool = False
    network_changed: bool = False
    persistence_changed: bool = False
    lifecycle_authority_exercised: bool = False
    business_result_changed: bool = False
    agent_effect: bool = False
    tool_effect: bool = False
    task_effect: bool = False
    audio_effect: bool = False
    history_effect: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.ready) is not bool
            or type(self.reason) is not CorrelationEvaluationReason
        ):
            raise ValueError("correlation evaluation has invalid truth fields")
        if self.ready != (self.correlation_map is not None) or self.ready != (
            self.reason is CorrelationEvaluationReason.READY
        ):
            raise ValueError("correlation readiness must match its exact result")
        if any(
            value is not False
            for value in (
                self.exporter_called,
                self.network_changed,
                self.persistence_changed,
                self.lifecycle_authority_exercised,
                self.business_result_changed,
                self.agent_effect,
                self.tool_effect,
                self.task_effect,
                self.audio_effect,
                self.history_effect,
            )
        ):
            raise ValueError("a pure correlation evaluation cannot own effects")


@dataclass(frozen=True, slots=True)
class CorrelationReplayEvaluation:
    accepted: bool
    reason: CorrelationReplayReason
    exporter_called: bool = False
    network_changed: bool = False
    persistence_changed: bool = False
    lifecycle_authority_exercised: bool = False
    business_result_changed: bool = False
    agent_effect: bool = False
    tool_effect: bool = False
    task_effect: bool = False
    audio_effect: bool = False
    history_effect: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.accepted) is not bool
            or type(self.reason) is not CorrelationReplayReason
        ):
            raise ValueError("correlation replay has invalid truth fields")
        if self.accepted != (self.reason is CorrelationReplayReason.IDEMPOTENT):
            raise ValueError("only an identical replay may be accepted")
        if any(
            value is not False
            for value in (
                self.exporter_called,
                self.network_changed,
                self.persistence_changed,
                self.lifecycle_authority_exercised,
                self.business_result_changed,
                self.agent_effect,
                self.tool_effect,
                self.task_effect,
                self.audio_effect,
                self.history_effect,
            )
        ):
            raise ValueError("correlation replay cannot own effects")


def _validated_map(
    candidate: ObservabilityCorrelationMap,
    trusted_receipt_verifier: object,
) -> ObservabilityCorrelationMap:
    if type(candidate.tokenization_receipt) is not CorrelationTokenizationReceipt:
        raise CorrelationContractViolation(
            "correlation map requires the exact tokenization receipt"
        )
    if type(candidate.metric_dimensions) is not BoundedMetricDimensions:
        raise CorrelationContractViolation(
            "metric dimensions require the exact bounded contract"
        )
    if type(candidate.metric_dimensions.labels) is not tuple or any(
        type(label) is not MetricDimension
        for label in candidate.metric_dimensions.labels
    ):
        raise CorrelationContractViolation(
            "metric dimensions contain a non-contract value"
        )
    if type(candidate.causation) is not tuple or any(
        type(link) is not CorrelationCausationLink for link in candidate.causation
    ):
        raise CorrelationContractViolation("causation contains a non-contract value")
    checked = ObservabilityCorrelationMap(
        contract_version=candidate.contract_version,
        map_id=candidate.map_id,
        correlation_id=candidate.correlation_id,
        subject_id=candidate.subject_id,
        project_id=candidate.project_id,
        session_id=candidate.session_id,
        tokenization_receipt=CorrelationTokenizationReceipt(
            contract_version=candidate.tokenization_receipt.contract_version,
            receipt_id=candidate.tokenization_receipt.receipt_id,
            issuer=candidate.tokenization_receipt.issuer,
            method=candidate.tokenization_receipt.method,
            scope_tag=candidate.tokenization_receipt.scope_tag,
            token_set_digest=candidate.tokenization_receipt.token_set_digest,
            raw_identity_included=(
                candidate.tokenization_receipt.raw_identity_included
            ),
        ),
        metric_dimensions=BoundedMetricDimensions(
            labels=tuple(
                MetricDimension(key=label.key, value=label.value)
                for label in candidate.metric_dimensions.labels
            )
        ),
        interaction_id=candidate.interaction_id,
        response_id=candidate.response_id,
        response_generation=candidate.response_generation,
        task_id=candidate.task_id,
        attempt_id=candidate.attempt_id,
        command_id=candidate.command_id,
        event_id=candidate.event_id,
        outbox_id=candidate.outbox_id,
        executor_id=candidate.executor_id,
        checkpoint_id=candidate.checkpoint_id,
        effect_id=candidate.effect_id,
        presentation_id=candidate.presentation_id,
        causation=tuple(
            CorrelationCausationLink(
                cause_kind=link.cause_kind,
                cause_id=link.cause_id,
                effect_kind=link.effect_kind,
                effect_id=link.effect_id,
            )
            for link in candidate.causation
        ),
    )
    if not callable(trusted_receipt_verifier):
        raise CorrelationContractViolation(
            "correlation readiness requires a trusted receipt verifier"
        )
    token_values = MappingProxyType(
        {
            field_name: getattr(checked, field_name)
            for field_name in (
                "map_id",
                "correlation_id",
                *_IDENTITY_FIELD_BY_KIND.values(),
            )
        }
    )
    try:
        verified = trusted_receipt_verifier(
            checked.tokenization_receipt,
            token_values,
        )
    except Exception as error:
        raise CorrelationContractViolation(
            "trusted receipt verification failed closed"
        ) from error
    if verified is not True:
        raise CorrelationContractViolation(
            "trusted receipt verifier rejected token provenance"
        )
    return checked


def evaluate_observability_correlation_map(
    candidate: object,
    *,
    enabled: bool,
    trusted_receipt_verifier: object = None,
) -> CorrelationEvaluation:
    """Revalidate one map relative to one injected owner trust anchor."""

    if type(enabled) is not bool:
        raise ValueError("enabled must be exact bool")
    if not enabled:
        return CorrelationEvaluation(
            ready=False,
            reason=CorrelationEvaluationReason.FEATURE_DISABLED,
            correlation_map=None,
        )
    if type(candidate) is not ObservabilityCorrelationMap:
        return CorrelationEvaluation(
            ready=False,
            reason=CorrelationEvaluationReason.INVALID_MAP,
            correlation_map=None,
        )
    try:
        checked = _validated_map(candidate, trusted_receipt_verifier)
    except PrivateCorrelationContent:
        return CorrelationEvaluation(
            ready=False,
            reason=CorrelationEvaluationReason.PRIVATE_CONTENT_REJECTED,
            correlation_map=None,
        )
    except Exception:
        return CorrelationEvaluation(
            ready=False,
            reason=CorrelationEvaluationReason.INVALID_MAP,
            correlation_map=None,
        )
    return CorrelationEvaluation(
        ready=True,
        reason=CorrelationEvaluationReason.READY,
        correlation_map=checked,
    )


def evaluate_observability_correlation_replay(
    original: object,
    replay: object,
    *,
    enabled: bool,
    trusted_receipt_verifier: object = None,
) -> CorrelationReplayEvaluation:
    """Accept one exact replay only after trusted provenance verification."""

    if type(enabled) is not bool:
        raise ValueError("enabled must be exact bool")
    if not enabled:
        return CorrelationReplayEvaluation(
            accepted=False,
            reason=CorrelationReplayReason.FEATURE_DISABLED,
        )
    if (
        type(original) is not ObservabilityCorrelationMap
        or type(replay) is not ObservabilityCorrelationMap
    ):
        return CorrelationReplayEvaluation(
            accepted=False,
            reason=CorrelationReplayReason.INVALID_MAP,
        )
    try:
        checked_original = _validated_map(original, trusted_receipt_verifier)
        checked_replay = _validated_map(replay, trusted_receipt_verifier)
    except Exception:
        return CorrelationReplayEvaluation(
            accepted=False,
            reason=CorrelationReplayReason.INVALID_MAP,
        )
    if checked_original.map_id != checked_replay.map_id:
        return CorrelationReplayEvaluation(
            accepted=False,
            reason=CorrelationReplayReason.IDENTITY_MISMATCH,
        )
    if checked_original != checked_replay:
        return CorrelationReplayEvaluation(
            accepted=False,
            reason=CorrelationReplayReason.CONFLICT,
        )
    return CorrelationReplayEvaluation(
        accepted=True,
        reason=CorrelationReplayReason.IDEMPOTENT,
    )


__all__ = [
    "BoundedMetricDimensions",
    "CorrelationCausationLink",
    "CorrelationContractViolation",
    "CorrelationEvaluation",
    "CorrelationEvaluationReason",
    "CorrelationIdentityKind",
    "CorrelationReplayEvaluation",
    "CorrelationReplayReason",
    "CorrelationTokenizationIssuer",
    "CorrelationTokenizationMethod",
    "CorrelationTokenizationReceipt",
    "CorrelationTokenizationReceiptVerifier",
    "CORRELATION_TOKENIZATION_RECEIPT_VERSION",
    "HIGH_CARDINALITY_TRACE_FIELD_ORDER",
    "HIGH_CARDINALITY_TRACE_FIELDS",
    "MAX_CORRELATION_IDENTITY_LENGTH",
    "MAX_CORRELATION_LINKS",
    "MAX_METRIC_DIMENSIONS",
    "MetricDimension",
    "MetricDimensionKey",
    "OBSERVABILITY_CORRELATION_CONTRACT_VERSION",
    "PUBLIC_CORRELATION_TOKEN_DIGEST_LENGTH",
    "PUBLIC_CORRELATION_TOKEN_VERSION",
    "ObservabilityCorrelationMap",
    "PrivateCorrelationContent",
    "evaluate_observability_correlation_map",
    "evaluate_observability_correlation_replay",
]
