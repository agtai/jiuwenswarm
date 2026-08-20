# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""In-memory presentation truth for the Live Voice CR-B runtime."""

from __future__ import annotations

import re
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    MAX_SAFE_INTEGER,
    Assurance,
    CommandEnvelope,
    ErrorCode,
    ResponseFence,
    ResponseRef,
    ResultEnvelope,
    ScopeRef,
)

from .formal_task_models import (
    TaskAuthorizationGrant,
    TaskResultRecord,
    TaskUnreadPage,
)


class PresentationLedgerViolation(ValueError):
    def __init__(self, reason: str, message: str, code: ErrorCode) -> None:
        super().__init__(message)
        self.reason = reason
        self.code = code


class TaskPresentationViolation(ValueError):
    """Safe failure at the TaskEvent-to-presentation consumption seam."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class PresentationSurface(StrEnum):
    TEXT = "text"
    AUDIO = "audio"


class HistorySurfacePolicy(StrEnum):
    TEXT = "text"
    AUDIO = "audio"
    UNION = "union"


class PresentationState(StrEnum):
    PRODUCED = "produced"
    ENQUEUED = "enqueued"
    PRESENTED = "presented"
    INVALIDATED = "invalidated"


_UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z$")


@dataclass(frozen=True, slots=True)
class PresentationUnit:
    ref: ResponseRef
    surface: PresentationSurface
    unit_id: str
    seq: int
    source_start_utf8: int
    source_end_utf8: int
    content_ref: str


@dataclass(frozen=True, slots=True)
class PresentationAck:
    ref: ResponseRef
    surface: PresentationSurface
    unit_id: str
    contiguous_cursor: int
    presented_at: str


@dataclass(frozen=True, slots=True)
class PresentationRecord:
    unit: PresentationUnit
    state: PresentationState
    presented_at: str | None = None
    invalidated_reason: str | None = None


@dataclass(frozen=True, slots=True)
class PresentedHistorySpan:
    ref: ResponseRef
    source_start_utf8: int
    source_end_utf8: int
    content_ref: str
    surfaces: tuple[PresentationSurface, ...]
    unit_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PresentationLedgerSnapshot:
    policies: tuple[tuple[ResponseRef, HistorySurfacePolicy], ...]
    records: tuple[PresentationRecord, ...]
    closed_surfaces: tuple[tuple[ResponseRef, PresentationSurface, str], ...]
    cursors: tuple[tuple[ResponseRef, PresentationSurface, int], ...]


class PresentationLedger:
    """Stores produced/enqueued/presented facts without owning external effects."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._policies: dict[ResponseRef, HistorySurfacePolicy] = {}
        self._records: dict[
            tuple[ResponseRef, PresentationSurface], list[PresentationRecord]
        ] = {}
        self._closed: dict[tuple[ResponseRef, PresentationSurface], str] = {}
        self._latest_ack: dict[
            tuple[ResponseRef, PresentationSurface], PresentationAck
        ] = {}
        self._ack_history: dict[
            tuple[ResponseRef, PresentationSurface], dict[int, PresentationAck]
        ] = {}

    def begin_response(self, ref: ResponseRef, policy: HistorySurfacePolicy) -> None:
        with self._lock:
            if not isinstance(policy, HistorySurfacePolicy):
                raise PresentationLedgerViolation(
                    "INVALID_HISTORY_SURFACE_POLICY",
                    "history policy must be text, audio, or union",
                    ErrorCode.INVALID_ARGUMENT,
                )
            if ref in self._policies:
                raise PresentationLedgerViolation(
                    "PRESENTATION_RESPONSE_ALREADY_EXISTS",
                    "presentation response identifiers cannot be reused",
                    ErrorCode.CONFLICT,
                )
            self._policies[ref] = policy
            for surface in PresentationSurface:
                self._records[(ref, surface)] = []

    def produce(self, unit: PresentationUnit) -> bool:
        with self._lock:
            self._validate_unit(unit)
            key = (unit.ref, unit.surface)
            self._require_open(key)
            records = self._records[key]

            for record in records:
                if record.unit.unit_id != unit.unit_id:
                    continue
                if record.unit == unit:
                    return False
                raise PresentationLedgerViolation(
                    "PRESENTATION_UNIT_REWRITE",
                    "a presentation unit identifier cannot be rewritten",
                    ErrorCode.CONFLICT,
                )

            expected_seq = len(records)
            if unit.seq != expected_seq:
                raise PresentationLedgerViolation(
                    "NON_CONTIGUOUS_PRESENTATION_SEQUENCE",
                    f"expected presentation sequence {expected_seq}",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            expected_start = 0 if not records else records[-1].unit.source_end_utf8
            if unit.source_start_utf8 != expected_start:
                raise PresentationLedgerViolation(
                    "NON_CONTIGUOUS_SOURCE_SPAN",
                    f"expected UTF-8 source byte offset {expected_start}",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            self._validate_cross_surface_alignment(unit)
            records.append(PresentationRecord(unit, PresentationState.PRODUCED))
            return True

    def enqueue(
        self, ref: ResponseRef, surface: PresentationSurface, unit_id: str
    ) -> tuple[bool, PresentationRecord]:
        with self._lock:
            key = self._key(ref, surface)
            self._require_open(key)
            index = self._unit_index(key, unit_id)
            record = self._records[key][index]
            if record.state is PresentationState.PRODUCED:
                updated = replace(record, state=PresentationState.ENQUEUED)
                self._records[key][index] = updated
                return True, updated
            if record.state is PresentationState.ENQUEUED:
                return False, record
            if record.state is PresentationState.PRESENTED:
                return False, record
            raise PresentationLedgerViolation(
                "PRESENTATION_UNIT_IMMUTABLE",
                "presented or invalidated units cannot be enqueued again",
                ErrorCode.CONFLICT,
            )

    def acknowledge(
        self, ack: PresentationAck
    ) -> tuple[bool, tuple[PresentationRecord, ...]]:
        with self._lock:
            self._validate_ack(ack)
            key = (ack.ref, ack.surface)
            self._require_open(key)
            records = self._records[key]
            if ack.contiguous_cursor >= len(records):
                raise PresentationLedgerViolation(
                    "ACK_BEYOND_PRODUCED_CURSOR",
                    "presentation acknowledgement is beyond produced content",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            target = records[ack.contiguous_cursor]
            if target.unit.unit_id != ack.unit_id:
                raise PresentationLedgerViolation(
                    "PRESENTATION_ACK_UNIT_MISMATCH",
                    "unit_id must identify the contiguous cursor target",
                    ErrorCode.PROTOCOL_VIOLATION,
                )

            prior_ack = self._latest_ack.get(key)
            prior_cursor = -1 if prior_ack is None else prior_ack.contiguous_cursor
            if ack.contiguous_cursor <= prior_cursor:
                existing = self._ack_history.get(key, {}).get(ack.contiguous_cursor)
                if existing == ack:
                    return False, ()
                if existing is not None:
                    raise PresentationLedgerViolation(
                        "PRESENTATION_ACK_REWRITE",
                        "an acknowledged cursor cannot be rewritten",
                        ErrorCode.CONFLICT,
                    )
                raise PresentationLedgerViolation(
                    "STALE_PRESENTATION_ACK",
                    "presentation acknowledgement cannot move backwards",
                    ErrorCode.STALE,
                )

            selected = records[prior_cursor + 1 : ack.contiguous_cursor + 1]
            if any(item.state is not PresentationState.ENQUEUED for item in selected):
                raise PresentationLedgerViolation(
                    "PRESENTATION_ACK_NOT_ENQUEUED",
                    "every newly acknowledged unit must already be enqueued",
                    ErrorCode.PROTOCOL_VIOLATION,
                )

            updated: list[PresentationRecord] = []
            for index in range(prior_cursor + 1, ack.contiguous_cursor + 1):
                item = replace(
                    records[index],
                    state=PresentationState.PRESENTED,
                    presented_at=ack.presented_at,
                )
                records[index] = item
                updated.append(item)
            self._latest_ack[key] = ack
            self._ack_history.setdefault(key, {})[ack.contiguous_cursor] = ack
            return True, tuple(updated)

    def close_surface(
        self, ref: ResponseRef, surface: PresentationSurface, *, reason: str
    ) -> tuple[bool, tuple[PresentationRecord, ...]]:
        with self._lock:
            reason = self._require_text(reason, "reason")
            key = self._key(ref, surface)
            if key in self._closed:
                return False, ()
            invalidated: list[PresentationRecord] = []
            records = self._records[key]
            for index, record in enumerate(records):
                if record.state in {
                    PresentationState.PRESENTED,
                    PresentationState.INVALIDATED,
                }:
                    continue
                updated = replace(
                    record,
                    state=PresentationState.INVALIDATED,
                    invalidated_reason=reason,
                )
                records[index] = updated
                invalidated.append(updated)
            self._closed[key] = reason
            return True, tuple(invalidated)

    def invalidate_response(
        self, ref: ResponseRef, *, reason: str
    ) -> tuple[PresentationRecord, ...]:
        with self._lock:
            self._require_response(ref)
            invalidated: list[PresentationRecord] = []
            for surface in PresentationSurface:
                _, records = self.close_surface(ref, surface, reason=reason)
                invalidated.extend(records)
            return tuple(invalidated)

    def presented_history(self, ref: ResponseRef) -> tuple[PresentedHistorySpan, ...]:
        with self._lock:
            policy = self._require_response(ref)
            selected: tuple[PresentationSurface, ...]
            if policy is HistorySurfacePolicy.TEXT:
                selected = (PresentationSurface.TEXT,)
            elif policy is HistorySurfacePolicy.AUDIO:
                selected = (PresentationSurface.AUDIO,)
            else:
                selected = tuple(PresentationSurface)

            by_fact: dict[
                tuple[int, int, str], list[tuple[PresentationSurface, str]]
            ] = {}
            content_by_span: dict[tuple[int, int], str] = {}
            for surface in selected:
                for record in self._records[(ref, surface)]:
                    if record.state is not PresentationState.PRESENTED:
                        continue
                    unit = record.unit
                    span = (unit.source_start_utf8, unit.source_end_utf8)
                    prior_content = content_by_span.setdefault(span, unit.content_ref)
                    if prior_content != unit.content_ref:
                        raise PresentationLedgerViolation(
                            "CROSS_SURFACE_CONTENT_CONFLICT",
                            "the same source span cannot select different content",
                            ErrorCode.CONFLICT,
                        )
                    fact = (*span, unit.content_ref)
                    by_fact.setdefault(fact, []).append((surface, unit.unit_id))

            result: list[PresentedHistorySpan] = []
            for (start, end, content_ref), owners in sorted(by_fact.items()):
                owners.sort(key=lambda item: item[0].value)
                result.append(
                    PresentedHistorySpan(
                        ref=ref,
                        source_start_utf8=start,
                        source_end_utf8=end,
                        content_ref=content_ref,
                        surfaces=tuple(item[0] for item in owners),
                        unit_ids=tuple(item[1] for item in owners),
                    )
                )
            return tuple(result)

    def snapshot(self) -> PresentationLedgerSnapshot:
        with self._lock:
            records = tuple(
                record for values in self._records.values() for record in values
            )
            return PresentationLedgerSnapshot(
                policies=tuple(self._policies.items()),
                records=records,
                closed_surfaces=tuple(
                    (ref, surface, reason)
                    for (ref, surface), reason in self._closed.items()
                ),
                cursors=tuple(
                    (ref, surface, ack.contiguous_cursor)
                    for (ref, surface), ack in self._latest_ack.items()
                ),
            )

    def _validate_unit(self, unit: PresentationUnit) -> None:
        if not isinstance(unit, PresentationUnit):
            raise PresentationLedgerViolation(
                "INVALID_PRESENTATION_UNIT",
                "presentation unit has an unsupported type",
                ErrorCode.INVALID_ARGUMENT,
            )
        self._require_response(unit.ref)
        if not isinstance(unit.surface, PresentationSurface):
            raise PresentationLedgerViolation(
                "INVALID_PRESENTATION_SURFACE",
                "presentation surface must be text or audio",
                ErrorCode.INVALID_ARGUMENT,
            )
        self._require_text(unit.unit_id, "unit_id")
        self._require_uint(unit.seq, "seq")
        self._require_uint(unit.source_start_utf8, "source_start_utf8")
        self._require_uint(unit.source_end_utf8, "source_end_utf8")
        if unit.source_end_utf8 <= unit.source_start_utf8:
            raise PresentationLedgerViolation(
                "EMPTY_PRESENTATION_SOURCE_SPAN",
                "presentation source span must contain at least one UTF-8 byte",
                ErrorCode.INVALID_ARGUMENT,
            )
        self._require_text(unit.content_ref, "content_ref")

    def _validate_ack(self, ack: PresentationAck) -> None:
        if not isinstance(ack, PresentationAck):
            raise PresentationLedgerViolation(
                "INVALID_PRESENTATION_ACK",
                "presentation acknowledgement has an unsupported type",
                ErrorCode.INVALID_ARGUMENT,
            )
        self._require_response(ack.ref)
        if not isinstance(ack.surface, PresentationSurface):
            raise PresentationLedgerViolation(
                "INVALID_PRESENTATION_SURFACE",
                "presentation surface must be text or audio",
                ErrorCode.INVALID_ARGUMENT,
            )
        self._require_text(ack.unit_id, "unit_id")
        self._require_uint(ack.contiguous_cursor, "contiguous_cursor")
        self._validate_utc(ack.presented_at)

    def _validate_cross_surface_alignment(self, unit: PresentationUnit) -> None:
        counterpart = (
            PresentationSurface.AUDIO
            if unit.surface is PresentationSurface.TEXT
            else PresentationSurface.TEXT
        )
        for record in self._records[(unit.ref, counterpart)]:
            other = record.unit
            overlaps = max(unit.source_start_utf8, other.source_start_utf8) < min(
                unit.source_end_utf8, other.source_end_utf8
            )
            if not overlaps:
                continue
            if (
                unit.seq != other.seq
                or unit.source_start_utf8 != other.source_start_utf8
                or unit.source_end_utf8 != other.source_end_utf8
                or unit.content_ref != other.content_ref
            ):
                raise PresentationLedgerViolation(
                    "CROSS_SURFACE_CONTENT_CONFLICT",
                    "overlapping union units must carry the same sequence, span, and content ref",
                    ErrorCode.CONFLICT,
                )

    def _key(
        self, ref: ResponseRef, surface: PresentationSurface
    ) -> tuple[ResponseRef, PresentationSurface]:
        self._require_response(ref)
        if not isinstance(surface, PresentationSurface):
            raise PresentationLedgerViolation(
                "INVALID_PRESENTATION_SURFACE",
                "presentation surface must be text or audio",
                ErrorCode.INVALID_ARGUMENT,
            )
        return ref, surface

    def _require_response(self, ref: ResponseRef) -> HistorySurfacePolicy:
        policy = self._policies.get(ref)
        if policy is None:
            raise PresentationLedgerViolation(
                "PRESENTATION_RESPONSE_NOT_FOUND",
                "presentation response requires an exact known response tuple",
                ErrorCode.NOT_FOUND,
            )
        return policy

    def _require_open(self, key: tuple[ResponseRef, PresentationSurface]) -> None:
        if key in self._closed:
            raise PresentationLedgerViolation(
                "PRESENTATION_SURFACE_CLOSED",
                "a closed presentation surface cannot advance",
                ErrorCode.STALE,
            )

    def _unit_index(
        self,
        key: tuple[ResponseRef, PresentationSurface],
        unit_id: str,
    ) -> int:
        unit_id = self._require_text(unit_id, "unit_id")
        for index, record in enumerate(self._records[key]):
            if record.unit.unit_id == unit_id:
                return index
        raise PresentationLedgerViolation(
            "PRESENTATION_UNIT_NOT_FOUND",
            "presentation unit does not exist on the exact surface",
            ErrorCode.NOT_FOUND,
        )

    @staticmethod
    def _require_text(value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise PresentationLedgerViolation(
                "INVALID_PRESENTATION_FIELD",
                f"{name} must be non-empty",
                ErrorCode.INVALID_ARGUMENT,
            )
        return value

    @staticmethod
    def _require_uint(value: int, name: str) -> int:
        if type(value) is not int or value < 0 or value > MAX_SAFE_INTEGER:
            raise PresentationLedgerViolation(
                "INVALID_PRESENTATION_COUNTER",
                f"{name} must be a non-negative safe integer",
                ErrorCode.INVALID_ARGUMENT,
            )
        return value

    @staticmethod
    def _validate_utc(value: str) -> None:
        if not isinstance(value, str) or _UTC_PATTERN.fullmatch(value) is None:
            raise PresentationLedgerViolation(
                "INVALID_PRESENTED_AT",
                "presented_at must be an RFC3339 UTC timestamp",
                ErrorCode.INVALID_ARGUMENT,
            )
        try:
            datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as error:
            raise PresentationLedgerViolation(
                "INVALID_PRESENTED_AT",
                "presented_at must be an RFC3339 UTC timestamp",
                ErrorCode.INVALID_ARGUMENT,
            ) from error


@dataclass(frozen=True, slots=True)
class TaskPresentationDelivery:
    """One ephemeral presentation attempt over a frozen durable unread head."""

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
            or self.scope.project_id is None
            or self.scope.session_id is None
        ):
            raise TaskPresentationViolation(
                "PRESENTATION_AUTHENTICATION_REQUIRED",
                "a presentation attempt requires a complete authenticated scope",
            )
        if self.presentation_class not in {"text", "voice"}:
            raise TaskPresentationViolation(
                "INVALID_PRESENTATION_CLASS",
                "presentation_class must be text or voice",
            )
        for field_name in (
            "task_id",
            "attempt_id",
            "event_id",
            "delivery_id",
            "unit_id",
        ):
            value = getattr(self, field_name)
            if type(value) is not str or not value.strip():
                raise TaskPresentationViolation(
                    "INVALID_PRESENTATION_IDENTITY",
                    f"{field_name} must be a non-empty exact identity",
                )
        if (
            type(self.event_seq) is not int
            or type(self.expected_event_head) is not int
            or not 0 <= self.event_seq <= self.expected_event_head <= MAX_SAFE_INTEGER
        ):
            raise TaskPresentationViolation(
                "INVALID_PRESENTATION_SEQUENCE",
                "presentation event must be inside its frozen unread head",
            )
        if self.result_source_event_id is not None and (
            type(self.result_source_event_id) is not str
            or not self.result_source_event_id.strip()
        ):
            raise TaskPresentationViolation(
                "INVALID_PRESENTATION_RESULT",
                "result_source_event_id must be an exact identity",
            )
        if not isinstance(self.response_ref, ResponseRef):
            raise TaskPresentationViolation(
                "INVALID_PRESENTATION_RESPONSE",
                "presentation attempt requires an exact response tuple",
            )

    @property
    def consumer_key(self) -> tuple[str, str, str, str]:
        assert self.scope.project_id is not None
        return (
            self.scope.subject_id,
            self.scope.project_id,
            self.task_id,
            self.presentation_class,
        )


@dataclass(frozen=True, slots=True)
class TextPresentationAdoptionAck:
    """Web-owner evidence that one exact text fact exists in the live DOM."""

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

    @classmethod
    def from_delivery(
        cls, delivery: TaskPresentationDelivery, *, adopted_at: str
    ) -> TextPresentationAdoptionAck:
        if not isinstance(delivery, TaskPresentationDelivery):
            raise TaskPresentationViolation(
                "INVALID_PRESENTATION_DELIVERY",
                "text adoption requires one exact delivery",
            )
        return cls(
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


class TaskPresentationConsumptionOwner:
    """Ephemeral ACK composition; durable truth remains in ``task.ack_events``.

    The owner deliberately has no Store, Task, Executor, network, DOM, TTS, audio,
    or history Port.  A caller may invoke its injected command Port only after the
    real Web or Runtime presentation owner supplies an exact accepted ACK.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._responses = ResponseFence()
        self._deliveries: dict[str, TaskPresentationDelivery] = {}
        self._text_acks: dict[str, TextPresentationAdoptionAck] = {}
        self._voice_acks: set[str] = set()

    def reserve_next(
        self,
        page: TaskUnreadPage,
        *,
        scope: ScopeRef,
        response_ref: ResponseRef,
        delivery_id: str,
        unit_id: str,
        result: TaskResultRecord | None = None,
    ) -> TaskPresentationDelivery:
        """Reserve only the next event of an authority-owned frozen prefix."""

        if not isinstance(page, TaskUnreadPage) or not page.events:
            raise TaskPresentationViolation(
                "PRESENTATION_UNREAD_EVENT_REQUIRED",
                "presentation reservation requires a non-empty unread page",
            )
        if (
            not isinstance(scope, ScopeRef)
            or scope.assurance is not Assurance.AUTHENTICATED
            or scope.project_id is None
            or scope.session_id is None
        ):
            raise TaskPresentationViolation(
                "PRESENTATION_AUTHENTICATION_REQUIRED",
                "presentation reservation requires a fresh authenticated scope",
            )
        event = page.events[0]
        if event.seq != page.watermark + 1:
            raise TaskPresentationViolation(
                "PRESENTATION_PREFIX_GAP",
                "only the next contiguous unread event may be reserved",
            )
        if (
            event.task_id != page.task_id
            or event.scope.subject_id != scope.subject_id
            or event.scope.project_id != scope.project_id
        ):
            raise TaskPresentationViolation(
                "PRESENTATION_SCOPE_MISMATCH",
                "unread event does not belong to the authenticated consumer scope",
            )

        terminal = event.event_type == "task.terminal"
        if terminal != (event.state == "terminal"):
            raise TaskPresentationViolation(
                "PRESENTATION_TERMINAL_MISMATCH",
                "terminal presentation requires the exact canonical terminal event",
            )

        completed = terminal and event.outcome == "completed"
        if completed:
            if (
                not isinstance(result, TaskResultRecord)
                or result.task_id != event.task_id
                or result.attempt_id != event.attempt_id
                or event.source_event_id is None
                or result.source_event_id != event.source_event_id
            ):
                raise TaskPresentationViolation(
                    "COMPLETED_RESULT_REQUIRED",
                    "completed presentation requires its exact legal TaskResult",
                )
            result_source_event_id = result.source_event_id
        else:
            if result is not None:
                raise TaskPresentationViolation(
                    "UNEXPECTED_PRESENTATION_RESULT",
                    "non-completed events cannot fabricate a TaskResult",
                )
            result_source_event_id = None

        delivery = TaskPresentationDelivery(
            scope=scope,
            presentation_class=page.presentation_class,
            task_id=event.task_id,
            attempt_id=event.attempt_id,
            event_id=event.event_id,
            event_seq=event.seq,
            expected_event_head=page.head_seq,
            result_source_event_id=result_source_event_id,
            response_ref=response_ref,
            delivery_id=delivery_id,
            unit_id=unit_id,
        )
        with self._lock:
            prior = self._deliveries.get(delivery.delivery_id)
            if prior is not None:
                if prior == delivery:
                    return prior
                raise TaskPresentationViolation(
                    "PRESENTATION_DELIVERY_REWRITE",
                    "delivery_id cannot be rebound to another attempt",
                )
            self._responses.begin(delivery.response_ref)
            self._deliveries[delivery.delivery_id] = delivery
        return delivery

    def mark_text_adopted(self, ack: TextPresentationAdoptionAck) -> bool:
        with self._lock:
            if not isinstance(ack, TextPresentationAdoptionAck):
                raise TaskPresentationViolation(
                    "INVALID_TEXT_ADOPTION_ACK",
                    "text adoption ACK has an unsupported type",
                )
            delivery = self._deliveries.get(ack.delivery_id)
            if delivery is None:
                raise TaskPresentationViolation(
                    "PRESENTATION_DELIVERY_NOT_FOUND",
                    "text adoption has no exact reserved delivery",
                )
            if delivery.presentation_class != "text":
                raise TaskPresentationViolation(
                    "TEXT_PRESENTATION_CLASS_REQUIRED",
                    "DOM adoption can consume only the text class",
                )
            expected = TextPresentationAdoptionAck.from_delivery(
                delivery, adopted_at=ack.adopted_at
            )
            self._validate_timestamp(ack.adopted_at)
            if ack != expected:
                raise TaskPresentationViolation(
                    "TEXT_ADOPTION_ACK_MISMATCH",
                    "text adoption ACK does not match its exact delivery tuple",
                )

            def apply() -> bool:
                prior = self._text_acks.get(delivery.delivery_id)
                if prior is not None:
                    if prior == ack:
                        return False
                    raise TaskPresentationViolation(
                        "TEXT_ADOPTION_ACK_REWRITE",
                        "accepted text adoption cannot be rewritten",
                    )
                self._text_acks[delivery.delivery_id] = ack
                return True

            return self._responses.apply_if_current(delivery.response_ref, apply)

    async def mark_voice_presented(
        self,
        delivery: TaskPresentationDelivery,
        ack: PresentationAck,
        runtime_ack_port: Callable[[PresentationAck], Awaitable[object]],
    ) -> bool:
        """Accept voice only through Runtime's canonical audio-ledger ACK Port."""

        with self._lock:
            owned = self._require_delivery(delivery)
            if owned.presentation_class != "voice":
                raise TaskPresentationViolation(
                    "VOICE_PRESENTATION_CLASS_REQUIRED",
                    "audio PresentationAck can consume only the voice class",
                )
            if not isinstance(ack, PresentationAck) or (
                ack.ref != owned.response_ref
                or ack.surface is not PresentationSurface.AUDIO
                or ack.unit_id != owned.unit_id
            ):
                raise TaskPresentationViolation(
                    "VOICE_PRESENTATION_ACK_MISMATCH",
                    "audio ACK does not match the exact delivery tuple",
                )
            if not callable(runtime_ack_port):
                raise TaskPresentationViolation(
                    "RUNTIME_PRESENTATION_ACK_UNAVAILABLE",
                    "voice presentation requires Runtime's audio ACK Port",
                )

        # Runtime owns TTS, the audio sink, and its presentation ledger.  Never
        # hold this composition lock while asking that external owner to mutate.
        outcome = await runtime_ack_port(ack)
        from .agent_conversation_runtime import PresentationAckResult

        if (
            not isinstance(outcome, PresentationAckResult)
            or outcome.ack != ack
            or not (outcome.accepted or outcome.replayed)
        ):
            raise TaskPresentationViolation(
                "RUNTIME_PRESENTATION_ACK_REJECTED",
                "Runtime did not accept the exact audio PresentationAck",
            )

        with self._lock:
            owned = self._require_delivery(delivery)

            def apply() -> bool:
                if owned.delivery_id in self._voice_acks:
                    return False
                self._voice_acks.add(owned.delivery_id)
                return True

            return self._responses.apply_if_current(owned.response_ref, apply)

    def consume(
        self,
        delivery: TaskPresentationDelivery,
        command: CommandEnvelope,
        authorization: TaskAuthorizationGrant,
        command_port: Callable[
            [CommandEnvelope, TaskAuthorizationGrant], ResultEnvelope
        ],
    ) -> ResultEnvelope:
        """Invoke the sole durable mutation only after an exact presentation ACK."""

        with self._lock:
            owned = self._require_delivery(delivery)
            accepted = (
                owned.delivery_id in self._text_acks
                if owned.presentation_class == "text"
                else owned.delivery_id in self._voice_acks
            )
            if not accepted:
                raise TaskPresentationViolation(
                    "PRESENTATION_ACK_REQUIRED",
                    "durable consumption requires an accepted presentation ACK",
                )
            if (
                not isinstance(command, CommandEnvelope)
                or command.command_type != "task.ack_events"
                or command.scope != owned.scope
                or command.target_ref.kind != "task"
                or command.target_ref.id != owned.task_id
                or command.required_capabilities != ("task.ack_events",)
                or command.payload
                != {
                    "presentation_class": owned.presentation_class,
                    "acked_through_seq": owned.event_seq,
                    "acked_event_id": owned.event_id,
                    "expected_event_head": owned.expected_event_head,
                }
            ):
                raise TaskPresentationViolation(
                    "CONSUMPTION_COMMAND_MISMATCH",
                    "task.ack_events command does not bind the accepted presentation",
                )
            if (
                not isinstance(authorization, TaskAuthorizationGrant)
                or authorization.scope != owned.scope
                or authorization.principal_id != owned.scope.subject_id
                or authorization.operation != "task.ack_events"
                or authorization.command_id != command.command_id
                or authorization.target_task_id != owned.task_id
                or authorization.allowed_capabilities != frozenset({"task.ack_events"})
            ):
                raise TaskPresentationViolation(
                    "CONSUMPTION_AUTHORIZATION_MISMATCH",
                    "consumption requires a new complete exact authorization grant",
                )
            if not callable(command_port):
                raise TaskPresentationViolation(
                    "CONSUMPTION_PORT_UNAVAILABLE",
                    "task.ack_events command Port is unavailable",
                )
        # Fresh authorization and the sole durable command Port are passed per
        # call.  This owner retains neither credential nor Core/Store authority.
        result = command_port(command, authorization)
        if not isinstance(result, ResultEnvelope):
            raise TaskPresentationViolation(
                "CONSUMPTION_RESULT_INVALID",
                "task.ack_events returned no canonical result",
            )
        if (
            result.request_id != command.request_id
            or result.command_id != command.command_id
        ):
            raise TaskPresentationViolation(
                "CONSUMPTION_RESULT_OWNER_MISMATCH",
                "task.ack_events result does not belong to the exact command",
            )
        if result.ok:
            value = result.result
            if (
                value is None
                or value.get("task_id") != owned.task_id
                or value.get("presentation_class") != owned.presentation_class
                or value.get("acked_through_seq") != owned.event_seq
                or value.get("acked_event_id") != owned.event_id
            ):
                raise TaskPresentationViolation(
                    "CONSUMPTION_RESULT_MISMATCH",
                    "task.ack_events result does not match the accepted presentation",
                )
        return result

    def _require_delivery(
        self, delivery: TaskPresentationDelivery
    ) -> TaskPresentationDelivery:
        if not isinstance(delivery, TaskPresentationDelivery):
            raise TaskPresentationViolation(
                "INVALID_PRESENTATION_DELIVERY",
                "presentation operation has an unsupported delivery type",
            )
        owned = self._deliveries.get(delivery.delivery_id)
        if owned is None or owned != delivery:
            raise TaskPresentationViolation(
                "PRESENTATION_DELIVERY_NOT_FOUND",
                "presentation operation does not match an exact reserved delivery",
            )
        return owned

    @staticmethod
    def _validate_timestamp(value: object) -> None:
        if type(value) is not str or _UTC_PATTERN.fullmatch(value) is None:
            raise TaskPresentationViolation(
                "INVALID_PRESENTATION_ACK_TIME",
                "presentation ACK time must be canonical UTC",
            )
        try:
            datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as error:
            raise TaskPresentationViolation(
                "INVALID_PRESENTATION_ACK_TIME",
                "presentation ACK time is invalid",
            ) from error
