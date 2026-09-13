# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Test-only presentation attempt oracle over existing Runtime value objects.

This module owns no durable state and deliberately has no Store/Core Port.
Tests must call the accepted P3-5A Port only after this harness accepts the
exact text-adoption or audio-presentation acknowledgement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    MAX_SAFE_INTEGER,
    Assurance,
    ResponseFence,
    ResponseRef,
    ScopeRef,
)
from jiuwenswarm.server.live_voice.presentation_ledger import (
    HistorySurfacePolicy,
    PresentationAck,
    PresentationLedger,
    PresentationSurface,
    PresentationUnit,
)


class PresentationOracleViolation(ValueError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def _text(value: object, field_name: str) -> str:
    if type(value) is not str or not value.strip():
        raise PresentationOracleViolation(
            "INVALID_PRESENTATION_IDENTITY", f"{field_name} must be non-empty"
        )
    return value


def _uint(value: object, field_name: str) -> int:
    if type(value) is not int or not 0 <= value <= MAX_SAFE_INTEGER:
        raise PresentationOracleViolation(
            "INVALID_PRESENTATION_IDENTITY",
            f"{field_name} must be a non-negative safe integer",
        )
    return value


def _timestamp(value: object, field_name: str) -> str:
    value = _text(value, field_name)
    if not value.endswith("Z"):
        raise PresentationOracleViolation(
            "INVALID_PRESENTATION_ACK", f"{field_name} must be UTC"
        )
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise PresentationOracleViolation(
            "INVALID_PRESENTATION_ACK", f"{field_name} is invalid"
        ) from error
    return value


@dataclass(frozen=True, slots=True)
class DeliveryAttempt:
    scope: ScopeRef
    presentation_class: str
    task_id: str
    attempt_id: str
    event_id: str
    event_seq: int
    expected_event_head: int
    result_source_event_id: str | None
    response_ref: ResponseRef
    delivery_id: str
    unit_id: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.scope, ScopeRef)
            or self.scope.assurance is not Assurance.AUTHENTICATED
        ):
            raise PresentationOracleViolation(
                "INVALID_PRESENTATION_SCOPE",
                "delivery requires one authenticated scope",
            )
        if self.presentation_class not in {"text", "voice"}:
            raise PresentationOracleViolation(
                "INVALID_PRESENTATION_CLASS", "delivery class must be text or voice"
            )
        for field_name in (
            "task_id",
            "attempt_id",
            "event_id",
            "delivery_id",
            "unit_id",
        ):
            _text(getattr(self, field_name), field_name)
        _uint(self.event_seq, "event_seq")
        _uint(self.expected_event_head, "expected_event_head")
        if self.event_seq > self.expected_event_head:
            raise PresentationOracleViolation(
                "PRESENTATION_EVENT_BEYOND_HEAD",
                "delivery event cannot exceed its frozen page head",
            )
        if self.result_source_event_id is not None:
            _text(self.result_source_event_id, "result_source_event_id")
        if not isinstance(self.response_ref, ResponseRef):
            raise PresentationOracleViolation(
                "INVALID_PRESENTATION_RESPONSE",
                "delivery requires an exact ResponseRef",
            )


@dataclass(frozen=True, slots=True)
class TextAdoptionAck:
    scope: ScopeRef
    presentation_class: str
    task_id: str
    attempt_id: str
    event_id: str
    event_seq: int
    expected_event_head: int
    result_source_event_id: str | None
    response_ref: ResponseRef
    delivery_id: str
    unit_id: str
    adopted_at: str


def text_adoption_ack(
    delivery: DeliveryAttempt,
    *,
    adopted_at: str = "2026-08-19T12:00:01Z",
) -> TextAdoptionAck:
    return TextAdoptionAck(
        scope=delivery.scope,
        presentation_class=delivery.presentation_class,
        task_id=delivery.task_id,
        attempt_id=delivery.attempt_id,
        event_id=delivery.event_id,
        event_seq=delivery.event_seq,
        expected_event_head=delivery.expected_event_head,
        result_source_event_id=delivery.result_source_event_id,
        response_ref=delivery.response_ref,
        delivery_id=delivery.delivery_id,
        unit_id=delivery.unit_id,
        adopted_at=adopted_at,
    )


@dataclass(frozen=True, slots=True)
class PresentationEffects:
    dom_adoptions: int
    audio_playouts: int
    network_calls: int
    tts_calls: int
    history_writes: int
    agent_calls: int
    tool_calls: int

    @property
    def legal_presentation_effects(self) -> int:
        return self.dom_adoptions + self.audio_playouts

    @property
    def external_effects(self) -> int:
        return (
            self.network_calls
            + self.tts_calls
            + self.history_writes
            + self.agent_calls
            + self.tool_calls
        )


class PresentationAttemptHarness:
    """In-memory exact-attempt oracle; intentionally discarded on crash."""

    def __init__(self) -> None:
        self._responses = ResponseFence()
        self._ledger = PresentationLedger()
        self._deliveries: dict[str, DeliveryAttempt] = {}
        self._published: set[str] = set()
        self._text_acks: dict[str, TextAdoptionAck] = {}
        self._voice_acks: set[str] = set()
        self._dom_adoptions = 0
        self._audio_playouts = 0

    def reserve(self, delivery: DeliveryAttempt) -> bool:
        if not isinstance(delivery, DeliveryAttempt):
            raise PresentationOracleViolation(
                "INVALID_PRESENTATION_DELIVERY", "delivery has an unsupported type"
            )
        existing = self._deliveries.get(delivery.delivery_id)
        if existing is not None:
            if existing == delivery:
                return False
            raise PresentationOracleViolation(
                "PRESENTATION_DELIVERY_REWRITE",
                "delivery identity cannot be rewritten",
            )
        self._responses.begin(delivery.response_ref)
        if delivery.presentation_class == "voice":
            self._ledger.begin_response(
                delivery.response_ref, HistorySurfacePolicy.AUDIO
            )
            unit = PresentationUnit(
                ref=delivery.response_ref,
                surface=PresentationSurface.AUDIO,
                unit_id=delivery.unit_id,
                seq=0,
                source_start_utf8=0,
                source_end_utf8=1,
                content_ref=delivery.event_id,
            )
            self._ledger.produce(unit)
            self._ledger.enqueue(
                delivery.response_ref, PresentationSurface.AUDIO, delivery.unit_id
            )
        self._deliveries[delivery.delivery_id] = delivery
        return True

    def publish(self, delivery: DeliveryAttempt) -> bool:
        owned = self._require_delivery(delivery)

        def apply() -> bool:
            if owned.delivery_id in self._published:
                return False
            self._published.add(owned.delivery_id)
            if owned.presentation_class == "text":
                self._dom_adoptions += 1
            else:
                self._audio_playouts += 1
            return True

        return self._responses.apply_if_current(owned.response_ref, apply)

    def accept_text(self, ack: TextAdoptionAck) -> bool:
        if not isinstance(ack, TextAdoptionAck):
            raise PresentationOracleViolation(
                "INVALID_TEXT_ADOPTION_ACK", "text ACK has an unsupported type"
            )
        owned = self._deliveries.get(ack.delivery_id)
        if owned is None or owned.presentation_class != "text":
            raise PresentationOracleViolation(
                "TEXT_ADOPTION_ACK_NOT_FOUND",
                "text ACK has no exact text delivery",
            )
        expected = text_adoption_ack(owned, adopted_at=ack.adopted_at)
        _timestamp(ack.adopted_at, "adopted_at")
        if ack != expected:
            raise PresentationOracleViolation(
                "TEXT_ADOPTION_ACK_MISMATCH",
                "text ACK does not match its exact delivery tuple",
            )

        def apply() -> bool:
            if owned.delivery_id not in self._published:
                raise PresentationOracleViolation(
                    "TEXT_NOT_ADOPTED", "text cannot be ACKed before DOM adoption"
                )
            prior = self._text_acks.get(owned.delivery_id)
            if prior is not None:
                if prior == ack:
                    return False
                raise PresentationOracleViolation(
                    "TEXT_ADOPTION_ACK_REWRITE", "text ACK cannot be rewritten"
                )
            self._text_acks[owned.delivery_id] = ack
            return True

        return self._responses.apply_if_current(owned.response_ref, apply)

    def accept_voice(self, delivery: DeliveryAttempt, ack: PresentationAck) -> bool:
        owned = self._require_delivery(delivery)
        if owned.presentation_class != "voice":
            raise PresentationOracleViolation(
                "VOICE_PRESENTATION_CLASS_MISMATCH",
                "audio PresentationAck cannot consume text",
            )

        def apply() -> bool:
            if owned.delivery_id not in self._published:
                raise PresentationOracleViolation(
                    "AUDIO_NOT_PLAYED", "audio cannot be ACKed before playout"
                )
            advanced, _records = self._ledger.acknowledge(ack)
            if advanced:
                self._voice_acks.add(owned.delivery_id)
            return advanced

        return self._responses.apply_if_current(owned.response_ref, apply)

    def presentation_accepted(self, delivery: DeliveryAttempt) -> bool:
        owned = self._require_delivery(delivery)
        if owned.presentation_class == "text":
            return owned.delivery_id in self._text_acks
        return owned.delivery_id in self._voice_acks

    def effects(self) -> PresentationEffects:
        return PresentationEffects(
            dom_adoptions=self._dom_adoptions,
            audio_playouts=self._audio_playouts,
            network_calls=0,
            tts_calls=0,
            history_writes=0,
            agent_calls=0,
            tool_calls=0,
        )

    def _require_delivery(self, delivery: DeliveryAttempt) -> DeliveryAttempt:
        if not isinstance(delivery, DeliveryAttempt):
            raise PresentationOracleViolation(
                "INVALID_PRESENTATION_DELIVERY", "delivery has an unsupported type"
            )
        owned = self._deliveries.get(delivery.delivery_id)
        if owned is None or owned != delivery:
            raise PresentationOracleViolation(
                "PRESENTATION_DELIVERY_MISMATCH",
                "operation does not match its exact delivery tuple",
            )
        return owned
