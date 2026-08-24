# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Async product-query owner over the isolated OpenJiuwen Task facade.

The projection is intentionally AgentCore-native and versioned. It does not
pretend to be the legacy Live Voice Task Core ``spec/attempt/admission`` shape.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ContractError,
    ErrorCode,
    IdentityKind,
    QueryEnvelope,
    ResultEnvelope,
)

from .formal_task_models import FormalTaskViolation, TaskAuthorizationGrant, utc_now
from .openjiuwen_task_facade import (
    OpenJiuwenTaskEvent,
    OpenJiuwenTaskExecution,
    OpenJiuwenTaskFacade,
    OpenJiuwenTaskResultRef,
    OpenJiuwenTaskSnapshot,
    derive_openjiuwen_scope_binding,
)
from .product_authority import P3AuthorityContext
from .product_p3_text_adapter import ProductP3AuthorizedQuery

_PROJECTION = "openjiuwen.agentcore.task-query.v1"
_OPERATIONS = frozenset(
    {"task.get", "task.list", "task.status", "task.events", "task.result"}
)
_MAX_LIST_LIMIT = 100
_MAX_EVENT_LIMIT = 500


def _contract_error(
    query: QueryEnvelope,
    *,
    code: ErrorCode,
    reason: str,
    message: str,
    retriable: bool = False,
) -> ContractError:
    return ContractError.from_dict(
        {
            "code": code.value,
            "reason": reason,
            "message": message,
            "retriable": retriable,
            "correlation_id": query.correlation_id,
            "details": {},
        }
    )


def _failure(
    query: QueryEnvelope,
    *,
    observed_at: str,
    code: ErrorCode,
    reason: str,
    message: str,
    retriable: bool = False,
) -> ResultEnvelope:
    return ResultEnvelope.failure(
        owner=query,
        error=_contract_error(
            query,
            code=code,
            reason=reason,
            message=message,
            retriable=retriable,
        ),
        observed_at=observed_at,
    )


def _result_ref_payload(
    value: OpenJiuwenTaskResultRef | None,
) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "result_id": value.result_id,
        "digest": value.digest,
        "locator": value.locator,
    }


def _execution_payload(
    value: OpenJiuwenTaskExecution | None,
) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "task_id": value.task_id,
        "execution_id": value.execution_id,
        "profile_digest": value.profile_digest,
        "generation": value.generation,
        "owner_id": value.owner_id,
        "owner_epoch": value.owner_epoch,
        "disposition": value.disposition,
        "execution_version": value.execution_version,
        "checkpoint_head": value.checkpoint_head,
        "outcome": value.outcome,
        "result_ref": _result_ref_payload(value.result_ref),
    }


def _snapshot_payload(value: OpenJiuwenTaskSnapshot) -> dict[str, object]:
    task = value.task
    return {
        "task": {
            "task_id": task.task_id,
            "title": task.title,
            "content": task.content,
            "status": task.status,
            "assignee": task.assignee,
            "current_execution_id": task.current_execution_id,
            "execution_version": task.execution_version,
            "event_head": task.event_head,
            "updated_at": task.updated_at,
        },
        "execution": _execution_payload(value.execution),
    }


def _event_payload(value: OpenJiuwenTaskEvent) -> dict[str, object]:
    return {
        "task_id": value.task_id,
        "sequence": value.sequence,
        "event_id": value.event_id,
        "event_type": value.event_type,
        "schema_version": value.schema_version,
        "producer": value.producer,
        "causation_id": value.causation_id,
        "correlation_id": value.correlation_id,
        "payload_json": value.payload_json,
        "payload_digest": value.payload_digest,
        "occurred_at": value.occurred_at,
        "execution_id": value.execution_id,
        "execution_version": value.execution_version,
    }


def _exact_payload(
    payload: object,
    keys: frozenset[str],
) -> Mapping[str, object] | None:
    if type(payload) is not dict or frozenset(payload) != keys:
        return None
    return payload


class OpenJiuwenProductP3QueryOwner:
    """Read-only async owner for one exact product scope and facade binding."""

    __slots__ = ("_facade",)

    def __init__(self, facade: OpenJiuwenTaskFacade) -> None:
        if not isinstance(facade, OpenJiuwenTaskFacade):
            raise ValueError("OpenJiuwen product query facade is required")
        if facade.executor_authority:
            raise ValueError("OpenJiuwen product query owner cannot execute")
        self._facade = facade

    @property
    def executor_authority(self) -> bool:
        return False

    async def query(
        self,
        query: ProductP3AuthorizedQuery,
        *,
        now: str | None = None,
    ) -> ResultEnvelope:
        observed_at = utc_now() if now is None else now
        if type(query) is not ProductP3AuthorizedQuery:
            raise TypeError("invalid OpenJiuwen product query")
        envelope = query.envelope
        context = query.authority
        grant = query.authorization
        if (
            not isinstance(envelope, QueryEnvelope)
            or type(context) is not P3AuthorityContext
            or type(grant) is not TaskAuthorizationGrant
            or envelope.scope != context.authority.scope
            or envelope.correlation_id != context.authority.correlation_id
            or context.command_id is not None
            or context.confirmation_id is not None
            or context.confirmation_binding is not None
            or context.intent_sha256 is not None
        ):
            raise ValueError("invalid OpenJiuwen product query binding")
        if envelope.query_type not in _OPERATIONS:
            return _failure(
                envelope,
                observed_at=observed_at,
                code=ErrorCode.UNSUPPORTED,
                reason="UNSUPPORTED_OPENJIUWEN_QUERY",
                message="OpenJiuwen query operation is unsupported",
            )
        if envelope.required_capabilities != (envelope.query_type,):
            raise ValueError("invalid OpenJiuwen product query capability")

        is_list = envelope.query_type == "task.list"
        target_task_id = None if is_list else envelope.target_ref.id
        if (
            envelope.target_ref.kind is not IdentityKind.TASK
            or (is_list and envelope.target_ref.id != "task-list")
            or (not is_list and context.target_task_id != target_task_id)
            or (is_list and context.target_task_id is not None)
        ):
            raise ValueError("invalid OpenJiuwen product query target")
        authority = context.authority
        expected_capabilities = frozenset({envelope.query_type})
        resource = context.resource
        expected_resource_digest = (
            None
            if target_task_id is None
            else hashlib.sha256(target_task_id.encode("utf-8")).hexdigest()
        )
        if derive_openjiuwen_scope_binding(authority.scope) != self._facade.binding or (
            target_task_id is None
            and resource is not None
            or target_task_id is not None
            and (
                resource is None
                or resource.kind != "task"
                or resource.resource_id != target_task_id
                or resource.fingerprint_sha256 != expected_resource_digest
            )
        ):
            return _failure(
                envelope,
                observed_at=observed_at,
                code=ErrorCode.PERMISSION_DENIED,
                reason="OPENJIUWEN_QUERY_AUTHORIZATION_DENIED",
                message="OpenJiuwen query authorization was denied",
            )
        expected_grant = TaskAuthorizationGrant(
            principal_id=authority.principal_id,
            scope=authority.scope,
            operation=authority.operation,
            command_id=None,
            target_task_id=target_task_id,
            allowed_capabilities=authority.capabilities,
            confirmation_id=None,
            confirmed=False,
            expires_at=authority.expires_at,
        )
        if (
            authority.operation != envelope.query_type
            or authority.capabilities != expected_capabilities
            or authority.confirmation is not None
            or grant != expected_grant
        ):
            return _failure(
                envelope,
                observed_at=observed_at,
                code=ErrorCode.PERMISSION_DENIED,
                reason="OPENJIUWEN_QUERY_AUTHORIZATION_DENIED",
                message="OpenJiuwen query authorization was denied",
            )
        try:
            grant.authorize(
                scope=envelope.scope,
                operation=envelope.query_type,
                command_id=None,
                target_task_id=target_task_id,
                required_capabilities=expected_capabilities,
                destructive=False,
                now=observed_at,
            )
        except FormalTaskViolation:
            return _failure(
                envelope,
                observed_at=observed_at,
                code=ErrorCode.PERMISSION_DENIED,
                reason="OPENJIUWEN_QUERY_AUTHORIZATION_DENIED",
                message="OpenJiuwen query authorization was denied",
            )

        if envelope.query_type == "task.list":
            payload = _exact_payload(envelope.payload, frozenset({"cursor", "limit"}))
            if payload is None:
                return _failure(
                    envelope,
                    observed_at=observed_at,
                    code=ErrorCode.INVALID_ARGUMENT,
                    reason="INVALID_OPENJIUWEN_LIST_QUERY",
                    message="OpenJiuwen list query payload is invalid",
                )
            cursor = payload["cursor"]
            limit = payload["limit"]
            if cursor is not None:
                try:
                    valid_cursor = (
                        type(cursor) is str
                        and bool(cursor.strip())
                        and "\x00" not in cursor
                        and len(cursor) <= 256
                        and bool(cursor.encode("utf-8"))
                    )
                except UnicodeEncodeError:
                    valid_cursor = False
                if not valid_cursor:
                    return _failure(
                        envelope,
                        observed_at=observed_at,
                        code=ErrorCode.INVALID_ARGUMENT,
                        reason="INVALID_OPENJIUWEN_LIST_QUERY",
                        message="OpenJiuwen list query payload is invalid",
                    )
                return _failure(
                    envelope,
                    observed_at=observed_at,
                    code=ErrorCode.CAPABILITY_UNAVAILABLE,
                    reason="OPENJIUWEN_LIST_CONTINUATION_UNAVAILABLE",
                    message="OpenJiuwen list continuation is unavailable",
                )
            if type(limit) is not int or not 1 <= limit <= _MAX_LIST_LIMIT:
                return _failure(
                    envelope,
                    observed_at=observed_at,
                    code=ErrorCode.INVALID_ARGUMENT,
                    reason="INVALID_OPENJIUWEN_LIST_QUERY",
                    message="OpenJiuwen list query payload is invalid",
                )
            snapshots = await self._facade.list(context.authority, limit=limit)
            return ResultEnvelope.success(
                owner=envelope,
                observed_at=observed_at,
                result={
                    "projection": _PROJECTION,
                    "tasks": [_snapshot_payload(item) for item in snapshots],
                    "cursor": None,
                    "limit": limit,
                    "returned_count": len(snapshots),
                    "boundary_reached": len(snapshots) == limit,
                    "continuation_supported": False,
                },
            )

        assert target_task_id is not None
        if envelope.query_type in {"task.get", "task.status", "task.result"}:
            if _exact_payload(envelope.payload, frozenset()) is None:
                return _failure(
                    envelope,
                    observed_at=observed_at,
                    code=ErrorCode.INVALID_ARGUMENT,
                    reason="INVALID_OPENJIUWEN_TASK_QUERY",
                    message="OpenJiuwen Task query payload is invalid",
                )
            if envelope.query_type == "task.result":
                result = await self._facade.read_result(
                    context.authority,
                    target_task_id,
                )
                if result is None:
                    return _failure(
                        envelope,
                        observed_at=observed_at,
                        code=ErrorCode.NOT_FOUND,
                        reason="OPENJIUWEN_TASK_NOT_FOUND",
                        message="OpenJiuwen Task was not found",
                    )
                result_payload: dict[str, object] = {
                    "projection": _PROJECTION,
                    "task_id": result.task_id,
                    "task_status": result.task_status,
                    "execution_id": result.execution_id,
                    "outcome": result.outcome,
                    "result_ref": _result_ref_payload(result.result_ref),
                }
            else:
                snapshot = (
                    await self._facade.get(context.authority, target_task_id)
                    if envelope.query_type == "task.get"
                    else await self._facade.status(context.authority, target_task_id)
                )
                if snapshot is None:
                    return _failure(
                        envelope,
                        observed_at=observed_at,
                        code=ErrorCode.NOT_FOUND,
                        reason="OPENJIUWEN_TASK_NOT_FOUND",
                        message="OpenJiuwen Task was not found",
                    )
                result_payload = {
                    "projection": _PROJECTION,
                    **_snapshot_payload(snapshot),
                }
            return ResultEnvelope.success(
                owner=envelope,
                result=result_payload,
                observed_at=observed_at,
            )

        payload = _exact_payload(envelope.payload, frozenset({"after_seq", "limit"}))
        if payload is None:
            return _failure(
                envelope,
                observed_at=observed_at,
                code=ErrorCode.INVALID_ARGUMENT,
                reason="INVALID_OPENJIUWEN_EVENT_QUERY",
                message="OpenJiuwen event query payload is invalid",
            )
        after_seq = payload["after_seq"]
        limit = payload["limit"]
        if (
            type(after_seq) is not int
            or after_seq < -1
            or type(limit) is not int
            or not 1 <= limit <= _MAX_EVENT_LIMIT
        ):
            return _failure(
                envelope,
                observed_at=observed_at,
                code=ErrorCode.INVALID_ARGUMENT,
                reason="INVALID_OPENJIUWEN_EVENT_QUERY",
                message="OpenJiuwen event query payload is invalid",
            )
        normalized_after = max(after_seq, 0)
        page = await self._facade.read_events(
            context.authority,
            target_task_id,
            after_sequence=normalized_after,
            limit=limit,
        )
        last_sequence = (
            normalized_after if not page.events else page.events[-1].sequence
        )
        has_more = last_sequence < page.head_sequence
        return ResultEnvelope.success(
            owner=envelope,
            observed_at=observed_at,
            result={
                "projection": _PROJECTION,
                "task_id": target_task_id,
                "after_seq": after_seq,
                "normalized_after_sequence": normalized_after,
                "events": [_event_payload(event) for event in page.events],
                "head_seq": page.head_sequence,
                "next_after_seq": last_sequence if has_more else None,
                "has_more": has_more,
                "limit": limit,
            },
        )


__all__ = ["OpenJiuwenProductP3QueryOwner"]
