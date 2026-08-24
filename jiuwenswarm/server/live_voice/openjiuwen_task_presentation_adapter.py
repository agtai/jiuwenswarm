# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Product-presentation ACK to OpenJiuwen cursor publication.

This module is intentionally uncomposed. It retains no cursor or presentation
truth and imports no AgentCore implementation module. The retained product
owner first proves a real DOM/audio presentation; the facade remains the only
durable cursor authority.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    MAX_SAFE_INTEGER,
    CommandEnvelope,
    ContractError,
    ErrorCode,
    ResultEnvelope,
)

from .formal_task_models import (
    FormalTaskViolation,
    TaskAuthorizationGrant,
    utc_now,
)
from .openjiuwen_task_facade import (
    OpenJiuwenCursorAdvanceDecision,
    OpenJiuwenTaskCursor,
    OpenJiuwenTaskEvent,
    OpenJiuwenTaskFacade,
    OpenJiuwenTaskFacadeError,
    OpenJiuwenTaskUnreadPage,
    derive_openjiuwen_scope_binding,
)
from .presentation_ledger import (
    TaskPresentationConsumptionOwner,
    TaskPresentationDelivery,
)
from .product_authority import ResolvedProductAuthority

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_EVENT_PAYLOAD_BYTES = 16_384
_MAX_EVENT_PAGE = 500
_MAX_ID_LENGTH = 255
_AGENTCORE_EVENT_TYPES = frozenset(
    {
        "task.created",
        "task.updated",
        "task.status_changed",
        "task.deleted",
        "task.dependencies_changed",
        "task.review_changed",
        "task.execution_prepared",
        "task.execution_admitted",
        "task.execution_reconciled",
        "task.execution_settled",
        "task.execution_checkpoint_published",
    }
)


class OpenJiuwenTaskPresentationAdapterError(RuntimeError):
    """Stable fail-closed error at the presentation/cursor boundary."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _error(reason: str) -> OpenJiuwenTaskPresentationAdapterError:
    return OpenJiuwenTaskPresentationAdapterError(reason)


def _text(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or not value.strip()
        or "\x00" in value
        or len(value) > _MAX_ID_LENGTH
    ):
        raise _error(f"INVALID_{field_name.upper()}")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise _error(f"INVALID_{field_name.upper()}") from None
    return value


def _integer(value: object, field_name: str, *, positive: bool = False) -> int:
    minimum = 1 if positive else 0
    if type(value) is not int or not minimum <= value <= MAX_SAFE_INTEGER:
        raise _error(f"INVALID_{field_name.upper()}")
    return value


def _digest(value: object, field_name: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise _error(f"INVALID_{field_name.upper()}")
    return value


def _canonical_event(
    event: object, *, task_id: str, sequence: int
) -> OpenJiuwenTaskEvent:
    if not isinstance(event, OpenJiuwenTaskEvent):
        raise _error("INVALID_AGENTCORE_EVENT")
    if (
        _text(event.task_id, "event_task_id") != task_id
        or _integer(event.sequence, "event_sequence", positive=True) != sequence
        or _text(event.event_id, "event_id") != event.event_id
        or _text(event.event_type, "event_type") not in _AGENTCORE_EVENT_TYPES
        or type(event.schema_version) is not int
        or event.schema_version != 1
        or not _text(event.producer, "event_producer")
        or not _text(event.causation_id, "event_causation_id")
        or not _text(event.correlation_id, "event_correlation_id")
        or type(event.payload_json) is not str
        or _integer(event.occurred_at, "event_occurred_at", positive=True)
        != event.occurred_at
    ):
        raise _error("INVALID_AGENTCORE_EVENT")
    payload_digest = _digest(event.payload_digest, "event_payload_digest")
    try:
        payload_bytes = event.payload_json.encode("utf-8")
        if len(payload_bytes) > _MAX_EVENT_PAYLOAD_BYTES:
            raise ValueError("payload too large")
        payload = json.loads(
            event.payload_json,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, UnicodeEncodeError):
        raise _error("INVALID_AGENTCORE_EVENT_PAYLOAD") from None
    if (
        type(payload) is not dict
        or canonical != event.payload_json
        or hashlib.sha256(payload_bytes).hexdigest() != payload_digest
    ):
        raise _error("INVALID_AGENTCORE_EVENT_PAYLOAD")
    if (event.execution_id is None) != (event.execution_version is None):
        raise _error("INVALID_AGENTCORE_EVENT_EXECUTION")
    if event.execution_id is not None:
        _text(event.execution_id, "event_execution_id")
        _integer(event.execution_version, "event_execution_version", positive=True)
    return event


def _bound_event(
    page: object,
    *,
    facade: OpenJiuwenTaskFacade,
    delivery: TaskPresentationDelivery,
) -> tuple[OpenJiuwenTaskUnreadPage, OpenJiuwenTaskEvent]:
    if not isinstance(page, OpenJiuwenTaskUnreadPage):
        raise _error("INVALID_AGENTCORE_UNREAD_PAGE")
    cursor = page.cursor
    binding = facade.binding
    if (
        not isinstance(cursor, OpenJiuwenTaskCursor)
        or type(page.has_more) is not bool
        or cursor.task_id != delivery.task_id
        or cursor.consumer_id != binding.consumer_id
        or cursor.channel != delivery.presentation_class
        or (cursor.sequence == 0) != (cursor.version == 0)
        or cursor.version > cursor.sequence
        or (cursor.sequence == 0)
        != (cursor.event_id is None and cursor.event_payload_digest is None)
    ):
        raise _error("AGENTCORE_CURSOR_BINDING_MISMATCH")
    sequence = _integer(cursor.sequence, "cursor_sequence")
    _integer(cursor.version, "cursor_version")
    if cursor.sequence > 0:
        _text(cursor.event_id, "cursor_event_id")
        _digest(cursor.event_payload_digest, "cursor_event_payload_digest")
    if cursor.updated_at is not None:
        _integer(cursor.updated_at, "cursor_updated_at")
    head = _integer(page.head_sequence, "event_head", positive=True)
    if (
        sequence > head
        or type(page.events) is not tuple
        or len(page.events) > _MAX_EVENT_PAGE
    ):
        raise _error("INVALID_AGENTCORE_UNREAD_PAGE")
    events = tuple(
        _canonical_event(
            event,
            task_id=delivery.task_id,
            sequence=sequence + index,
        )
        for index, event in enumerate(page.events, start=1)
    )
    page_end = sequence + len(events)
    expected_next = page_end if page_end < head else None
    if page.next_after_sequence is not None:
        _integer(
            page.next_after_sequence,
            "next_after_sequence",
            positive=True,
        )
    if (
        (not events and sequence != head)
        or page_end > head
        or page.has_more is not (page_end < head)
        or page.next_after_sequence != expected_next
    ):
        raise _error("INVALID_AGENTCORE_UNREAD_PAGE")
    if (
        delivery.expected_event_head + 1 != head
        or delivery.event_seq + 1 <= sequence
        or delivery.event_seq + 1 > page_end
    ):
        raise _error("PRESENTATION_CURSOR_HEAD_MISMATCH")
    acknowledged = events[delivery.event_seq + 1 - sequence - 1]
    if (
        acknowledged.event_id != delivery.event_id
        or acknowledged.execution_id is None
        or acknowledged.execution_id != delivery.attempt_id
    ):
        raise _error("PRESENTATION_EVENT_BINDING_MISMATCH")
    return page, acknowledged


def _advance_id(facade: OpenJiuwenTaskFacade, command_id: str) -> str:
    command_id = _text(command_id, "command_id")
    digest = hashlib.sha256(
        b"livevoice.openjiuwen.presentation-advance.v1\x00"
        + facade.binding.team_name.encode("utf-8")
        + b"\x00"
        + command_id.encode("utf-8")
    ).hexdigest()
    return f"lv-oj-presentation-{digest}"


def _require_authority(
    facade: OpenJiuwenTaskFacade,
    authority: object,
    delivery: TaskPresentationDelivery,
    command: object,
    authorization: object,
    *,
    observed_at: str,
) -> tuple[CommandEnvelope, TaskAuthorizationGrant, ResolvedProductAuthority]:
    if (
        not isinstance(command, CommandEnvelope)
        or not isinstance(authorization, TaskAuthorizationGrant)
        or not isinstance(authority, ResolvedProductAuthority)
    ):
        raise _error("INVALID_PRESENTATION_CURSOR_AUTHORITY")
    resource_digest = hashlib.sha256(delivery.task_id.encode("utf-8")).hexdigest()
    resource = authority.resource
    if (
        derive_openjiuwen_scope_binding(delivery.scope) != facade.binding
        or authority.scope != delivery.scope
        or authority.operation != "task.ack_events"
        or authority.capabilities != frozenset({"task.ack_events"})
        or authority.correlation_id != command.correlation_id
        or authority.confirmation is not None
        or resource is None
        or resource.kind != "task"
        or resource.resource_id != delivery.task_id
        or resource.fingerprint_sha256 != resource_digest
    ):
        raise _error("PRESENTATION_CURSOR_AUTHORITY_MISMATCH")
    expected_grant = TaskAuthorizationGrant(
        principal_id=authority.principal_id,
        scope=authority.scope,
        operation="task.ack_events",
        command_id=command.command_id,
        target_task_id=delivery.task_id,
        allowed_capabilities=frozenset({"task.ack_events"}),
        confirmation_id=None,
        confirmed=False,
        expires_at=authority.expires_at,
        policy_bypass=authorization.policy_bypass,
    )
    if authorization != expected_grant or authorization.policy_bypass not in {
        None,
        "server_task_presentation_v1",
    }:
        raise _error("PRESENTATION_CURSOR_AUTHORIZATION_MISMATCH")
    try:
        authorization.authorize(
            scope=delivery.scope,
            operation="task.ack_events",
            command_id=command.command_id,
            target_task_id=delivery.task_id,
            required_capabilities=frozenset({"task.ack_events"}),
            destructive=False,
            now=observed_at,
        )
    except FormalTaskViolation:
        raise _error("PRESENTATION_CURSOR_AUTHORIZATION_REJECTED") from None
    return command, authorization, authority


def _failure(command: CommandEnvelope, *, observed_at: str) -> ResultEnvelope:
    return ResultEnvelope.failure(
        owner=command,
        observed_at=observed_at,
        error=ContractError.from_dict(
            {
                "code": ErrorCode.CONFLICT.value,
                "reason": "AGENTCORE_CURSOR_ADVANCE_REJECTED",
                "message": "AgentCore rejected the exact presentation cursor advance",
                "retriable": False,
                "correlation_id": command.correlation_id,
                "details": {},
            }
        ),
    )


class OpenJiuwenTaskPresentationCursorAdapter:
    """Publish one product-verified presentation ACK to AgentCore."""

    __slots__ = ("_facade",)

    def __init__(self, facade: OpenJiuwenTaskFacade) -> None:
        if not isinstance(facade, OpenJiuwenTaskFacade) or facade.executor_authority:
            raise ValueError("OpenJiuwen presentation cursor facade is required")
        self._facade = facade

    @property
    def executor_authority(self) -> bool:
        return False

    async def consume(
        self,
        owner: TaskPresentationConsumptionOwner,
        delivery: TaskPresentationDelivery,
        command: CommandEnvelope,
        authorization: TaskAuthorizationGrant,
        authority: ResolvedProductAuthority,
        unread_page: OpenJiuwenTaskUnreadPage,
        *,
        observed_at: str | None = None,
    ) -> ResultEnvelope:
        timestamp = utc_now() if observed_at is None else observed_at
        if not isinstance(owner, TaskPresentationConsumptionOwner):
            raise _error("INVALID_PRESENTATION_OWNER")
        page, event = _bound_event(
            unread_page,
            facade=self._facade,
            delivery=delivery,
        )
        command, authorization, authority = _require_authority(
            self._facade,
            authority,
            delivery,
            command,
            authorization,
            observed_at=timestamp,
        )
        advance_id = _advance_id(self._facade, command.command_id)

        async def advance(
            item: CommandEnvelope,
            grant: TaskAuthorizationGrant,
        ) -> ResultEnvelope:
            if item != command or grant != authorization:
                raise _error("PRESENTATION_CURSOR_CALL_REBOUND")
            try:
                decision = await self._facade.advance_after_presentation_ack(
                    authority,
                    delivery.task_id,
                    delivery.presentation_class,
                    advance_id,
                    expected_cursor_sequence=page.cursor.sequence,
                    expected_cursor_version=page.cursor.version,
                    expected_head_sequence=page.head_sequence,
                    acknowledged_sequence=event.sequence,
                    acknowledged_event_id=event.event_id,
                    acknowledged_event_payload_digest=event.payload_digest,
                )
            except asyncio.CancelledError:
                raise
            except OpenJiuwenTaskFacadeError as error:
                raise _error("AGENTCORE_CURSOR_ADVANCE_FAILED") from error
            if not isinstance(decision, OpenJiuwenCursorAdvanceDecision):
                raise _error("INVALID_AGENTCORE_CURSOR_DECISION")
            if (
                type(decision.ok) is not bool
                or type(decision.replayed) is not bool
                or type(decision.advanced) is not bool
                or type(decision.reason) is not str
            ):
                raise _error("INVALID_AGENTCORE_CURSOR_DECISION")
            if not decision.ok:
                return _failure(command, observed_at=timestamp)
            cursor = decision.cursor
            if (
                decision.advance_id != advance_id
                or cursor is None
                or cursor.task_id != delivery.task_id
                or cursor.consumer_id != self._facade.binding.consumer_id
                or cursor.channel != delivery.presentation_class
                or cursor.sequence < event.sequence
                or cursor.version < page.cursor.version
                or (
                    cursor.sequence == event.sequence
                    and (
                        cursor.event_id != event.event_id
                        or cursor.event_payload_digest != event.payload_digest
                    )
                )
            ):
                raise _error("INVALID_AGENTCORE_CURSOR_DECISION")
            return ResultEnvelope.success(
                owner=command,
                observed_at=timestamp,
                result={
                    "task_id": delivery.task_id,
                    "presentation_class": delivery.presentation_class,
                    "acked_through_seq": delivery.event_seq,
                    "acked_event_id": delivery.event_id,
                    "advanced": decision.advanced,
                    "replayed": decision.replayed,
                    "cursor_sequence": cursor.sequence,
                    "cursor_version": cursor.version,
                },
            )

        return await owner.consume_async(
            delivery,
            command,
            authorization,
            advance,
        )


__all__ = [
    "OpenJiuwenTaskPresentationAdapterError",
    "OpenJiuwenTaskPresentationCursorAdapter",
]
