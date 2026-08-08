# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Formal persistent P3-alpha Task Core and durable outbox orchestration."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import ClassVar, Protocol

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    CommandEnvelope,
    ContractViolation,
    ErrorCode,
    QueryEnvelope,
    ResultEnvelope,
    WorkProgressEventV2,
)

from .formal_task_models import (
    ExecutorDeliveryResult,
    ExecutorObservation,
    ExecutorResolution,
    FormalTaskSpec,
    FormalTaskViolation,
    OutboxKind,
    PersistentAttemptRecord,
    PersistentOutboxItem,
    PersistentTaskEvent,
    PersistentTaskRecord,
    ResolvedTaskContext,
    TaskAuthorizationGrant,
    require_exact_payload,
    utc_now,
)
from .task_store import SqliteTaskStore

_PROJECTABLE_TASK_EVENTS = frozenset(
    {
        "task.accepted",
        "task.running",
        "task.blocked",
        "task.decision_required",
        "task.terminal",
    }
)
_OUTBOX_CLAIM_LEASE = timedelta(minutes=5)


class FormalExecutor(Protocol):
    executor_id: str

    async def dispatch(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
        """Idempotently accept the exact formal attempt."""

    async def cancel(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
        """Request cancellation of the exact bound attempt."""

    async def status(
        self, task: PersistentTaskRecord, attempt: PersistentAttemptRecord
    ) -> ExecutorDeliveryResult | ExecutorObservation:
        """Resolve an original attempt after dispatch or process restart."""


def _contract_error(error: FormalTaskViolation) -> ContractViolation:
    return ContractViolation(
        error.code,
        error.reason,
        str(error),
        retriable=error.code
        in {ErrorCode.UNAVAILABLE, ErrorCode.TIMEOUT, ErrorCode.RESULT_UNKNOWN},
    )


def _failure(
    owner: CommandEnvelope | QueryEnvelope,
    error: FormalTaskViolation,
    *,
    observed_at: str,
) -> ResultEnvelope:
    return ResultEnvelope.failure(
        owner=owner,
        error=_contract_error(error).error,
        observed_at=observed_at,
    )


def project_task_event(event: PersistentTaskEvent) -> dict[str, object]:
    """Pure TaskEvent -> WorkProgress projection; never mutates or invokes TTS."""

    if event.event_type not in _PROJECTABLE_TASK_EVENTS:
        raise FormalTaskViolation(
            "TASK_EVENT_NOT_PROJECTABLE",
            "attempt/control/internal events cannot emit duplicate task progress",
            ErrorCode.PROTOCOL_VIOLATION,
        )
    terminal = event.state == "terminal"
    if terminal != (event.outcome is not None):
        raise FormalTaskViolation(
            "INVALID_TASK_PROGRESS_SOURCE",
            "terminal progress and outcome must agree",
            ErrorCode.PROTOCOL_VIOLATION,
        )
    details = event.details
    summary = details.get("summary")
    if summary is not None and type(summary) is not str:
        summary = None
    payload = {
        "work_ref": {"kind": "task", "id": event.task_id},
        "source": {
            "authority": "task_core",
            "event_id": event.event_id,
            "source_work_ref": {"kind": "task", "id": event.task_id},
            "adapter": (
                None if event.producer.startswith("task_core") else event.producer
            ),
        },
        "seq": event.seq,
        "state": event.state,
        "outcome": event.outcome,
        "summary": (
            {"knowledge": "unknown"}
            if summary is None
            else {"knowledge": "known", "value": summary}
        ),
        "blocking_question": {"knowledge": "unknown"},
        "artifact_refs": {"knowledge": "unknown"},
        "urgency": "unknown",
        "speakability": "not_speakable",
    }
    try:
        return WorkProgressEventV2.from_dict(payload).to_dict()
    except ContractViolation as error:
        raise FormalTaskViolation(
            "INVALID_TASK_PROGRESS_PROJECTION",
            f"Task Core produced invalid WorkProgress: {error}",
            ErrorCode.PROTOCOL_VIOLATION,
        ) from error


ReconciliationEventSink = Callable[
    [PersistentTaskEvent, PersistentAttemptRecord], Awaitable[None]
]


class PersistentTaskCore:
    """Owns formal task state; the Executor only reports attempt facts."""

    _CREATE_PAYLOAD: ClassVar[frozenset[str]] = frozenset(
        {
            "name",
            "instruction",
            "executor_id",
            "side_effect_class",
            "attributes",
        }
    )

    def __init__(
        self,
        store: SqliteTaskStore,
        executor: FormalExecutor,
        *,
        reconciliation_event_sink: ReconciliationEventSink | None = None,
    ) -> None:
        self.store = store
        self.executor = executor
        self._reconciliation_event_sink = reconciliation_event_sink

    async def _publish_reconciliation_events(
        self,
        task: PersistentTaskRecord,
        *,
        after_seq: int,
    ) -> None:
        """Publish only durable events appended by an actual reconciliation.

        Evidence is deliberately downstream of the Store transaction.  A sink
        failure can neither roll back nor reinterpret the Task/Attempt truth.
        """

        sink = self._reconciliation_event_sink
        if sink is None:
            return
        attempt = self.store.get_attempt(task.attempt_id)
        events = self.store.events(task.task_id, task.scope, after_seq=after_seq)
        for event in events:
            try:
                await sink(event, attempt)
            except Exception:  # noqa: BLE001 -- evidence never owns Task truth
                continue

    def execute(
        self,
        command: CommandEnvelope,
        authorization: TaskAuthorizationGrant | None,
        *,
        context: ResolvedTaskContext | None = None,
        now: str | None = None,
    ) -> ResultEnvelope:
        observed_at = now or utc_now()
        try:
            if authorization is None:
                raise FormalTaskViolation(
                    "FORMAL_TASK_AUTHORIZATION_REQUIRED",
                    "formal task command requires trusted authorization",
                    ErrorCode.UNAUTHENTICATED,
                )
            if command.command_type not in {"task.create", "task.cancel"}:
                raise FormalTaskViolation(
                    "UNSUPPORTED_FORMAL_TASK_COMMAND",
                    "formal P3-alpha supports only task.create and task.cancel",
                    ErrorCode.UNSUPPORTED,
                )
            if command.target_ref.kind != "task":
                raise FormalTaskViolation(
                    "FORMAL_TASK_TARGET_MISMATCH",
                    "formal task commands require a task target reference",
                    ErrorCode.INVALID_ARGUMENT,
                )
            expected_target_id = (
                f"create:{command.command_id}"
                if command.command_type == "task.create"
                else command.target_ref.id
            )
            if command.target_ref.id != expected_target_id:
                raise FormalTaskViolation(
                    "FORMAL_TASK_TARGET_MISMATCH",
                    "task.create target must bind the exact command identity",
                    ErrorCode.INVALID_ARGUMENT,
                )
            expected_capabilities = frozenset({command.command_type})
            if frozenset(command.required_capabilities) != expected_capabilities:
                raise FormalTaskViolation(
                    "FORMAL_TASK_CAPABILITY_MISMATCH",
                    "formal task command must require its exact operation capability",
                    ErrorCode.PERMISSION_DENIED,
                )
            target_task_id = (
                None if command.command_type == "task.create" else command.target_ref.id
            )
            authorization.authorize(
                scope=command.scope,
                operation=command.command_type,
                command_id=command.command_id,
                target_task_id=target_task_id,
                required_capabilities=expected_capabilities,
                destructive=True,
                now=observed_at,
            )
            if command.command_type == "task.cancel":
                require_exact_payload(
                    command.payload, frozenset(), field_name="task.cancel payload"
                )
                return self.store.cancel(command, observed_at=observed_at)
            if context is None:
                raise FormalTaskViolation(
                    "FORMAL_TASK_CONTEXT_REQUIRED",
                    "task.create requires a server-resolved execution context",
                    ErrorCode.PERMISSION_DENIED,
                )
            context.require_usable(
                scope=command.scope,
                required_permissions=frozenset({"task.execute", "project.write"}),
                destructive=True,
                now=observed_at,
            )
            payload = command.payload
            require_exact_payload(
                payload, self._CREATE_PAYLOAD, field_name="task.create payload"
            )
            attributes = payload["attributes"]
            if type(attributes) is not dict or any(
                type(key) is not str or type(value) is not str
                for key, value in attributes.items()
            ):
                raise FormalTaskViolation(
                    "INVALID_FORMAL_TASK_ATTRIBUTES",
                    "task attributes must be a string map",
                    ErrorCode.INVALID_ARGUMENT,
                )
            if set(attributes) != {"model_identity", "model_config_version"}:
                raise FormalTaskViolation(
                    "INVALID_FORMAL_TASK_ATTRIBUTES",
                    "project Code Agent tasks require an exact resolved model binding",
                    ErrorCode.INVALID_ARGUMENT,
                )
            spec = FormalTaskSpec(
                name=payload["name"],
                instruction=payload["instruction"],
                origin=command.origin,
                context=context,
                executor_id=payload["executor_id"],
                required_capabilities=tuple(command.required_capabilities),
                side_effect_class=payload["side_effect_class"],
                attributes=tuple(sorted(attributes.items())),
            )
            if spec.executor_id != self.executor.executor_id:
                raise FormalTaskViolation(
                    "EXECUTOR_CAPABILITY_UNAVAILABLE",
                    "requested Executor is not available in this Task Core",
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                )
            if spec.side_effect_class != "project_mutation":
                raise FormalTaskViolation(
                    "EXECUTOR_SIDE_EFFECT_CLASS_MISMATCH",
                    "project Code Agent tasks require project_mutation side effects",
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                )
            return self.store.create(command, spec, observed_at=observed_at)
        except FormalTaskViolation as error:
            return _failure(command, error, observed_at=observed_at)

    def query(
        self,
        query: QueryEnvelope,
        authorization: TaskAuthorizationGrant | None,
        *,
        now: str | None = None,
    ) -> ResultEnvelope:
        observed_at = now or utc_now()
        try:
            if authorization is None:
                raise FormalTaskViolation(
                    "FORMAL_TASK_AUTHORIZATION_REQUIRED",
                    "formal task query requires trusted authorization",
                    ErrorCode.UNAUTHENTICATED,
                )
            if query.target_ref.kind != "task":
                raise FormalTaskViolation(
                    "FORMAL_TASK_TARGET_MISMATCH",
                    "formal task queries require a task target reference",
                    ErrorCode.INVALID_ARGUMENT,
                )
            target_task_id = (
                None if query.query_type == "task.list" else query.target_ref.id
            )
            expected_capabilities = frozenset({query.query_type})
            if frozenset(query.required_capabilities) != expected_capabilities:
                raise FormalTaskViolation(
                    "FORMAL_TASK_CAPABILITY_MISMATCH",
                    "formal task query must require its exact operation capability",
                    ErrorCode.PERMISSION_DENIED,
                )
            authorization.authorize(
                scope=query.scope,
                operation=query.query_type,
                command_id=None,
                target_task_id=target_task_id,
                required_capabilities=expected_capabilities,
                destructive=False,
                now=observed_at,
            )
            if query.query_type == "task.list":
                if query.target_ref.id != "task-list":
                    raise FormalTaskViolation(
                        "FORMAL_TASK_TARGET_MISMATCH",
                        "task.list requires its canonical collection target",
                        ErrorCode.INVALID_ARGUMENT,
                    )
                require_exact_payload(
                    query.payload, frozenset(), field_name="task.list payload"
                )
                result: Mapping[str, object] = {
                    "tasks": [
                        task.to_dict() for task in self.store.list_tasks(query.scope)
                    ]
                }
            elif query.query_type in {"task.get", "task.status"}:
                require_exact_payload(
                    query.payload,
                    frozenset(),
                    field_name=f"{query.query_type} payload",
                )
                task = self.store.get_task(query.target_ref.id, query.scope)
                result = {
                    "task": task.to_dict(),
                    "attempt": self.store.get_attempt(task.attempt_id).to_dict(),
                }
            elif query.query_type == "task.events":
                payload = query.payload
                if set(payload) - {"after_seq"}:
                    raise FormalTaskViolation(
                        "INVALID_TASK_EVENTS_QUERY",
                        "task.events query has unknown payload fields",
                        ErrorCode.INVALID_ARGUMENT,
                    )
                after_seq = payload.get("after_seq", -1)
                task = self.store.get_task(query.target_ref.id, query.scope)
                events = self.store.events(
                    query.target_ref.id, query.scope, after_seq=after_seq
                )
                result = {
                    "task_id": query.target_ref.id,
                    "after_seq": after_seq,
                    "events": [event.to_dict() for event in events],
                    "head_seq": task.event_head,
                    "truncated": False,
                    "cursor_replay_supported": False,
                }
            else:
                raise FormalTaskViolation(
                    "UNSUPPORTED_FORMAL_TASK_QUERY",
                    "formal P3-alpha query is unsupported",
                    ErrorCode.UNSUPPORTED,
                )
            return ResultEnvelope.success(
                owner=query,
                result=result,
                observed_at=observed_at,
            )
        except FormalTaskViolation as error:
            return _failure(query, error, observed_at=observed_at)

    async def drain_outbox_once(self, *, worker_id: str | None = None) -> bool:
        worker = worker_id or f"task-core-{uuid.uuid4().hex}"
        item = self.store.claim_outbox(worker)
        if item is None:
            return False
        try:
            if item.kind is OutboxKind.ATTEMPT_DISPATCH:
                delivery = await self.executor.dispatch(item)
            else:
                delivery = await self.executor.cancel(item)
        except FormalTaskViolation as error:
            if error.code in {
                ErrorCode.UNAVAILABLE,
                ErrorCode.TIMEOUT,
                ErrorCode.RESULT_UNKNOWN,
            }:
                self.store.release_outbox(item, str(error))
                raise
            self.store.reject_outbox(item, error)
            return True
        except Exception as error:
            self.store.release_outbox(item, str(error))
            raise
        if item.kind is OutboxKind.ATTEMPT_DISPATCH and not delivery.observations:
            self.store.release_outbox(
                item, "dispatch returned no accepted Executor evidence"
            )
            raise FormalTaskViolation(
                "EXECUTOR_DISPATCH_RESULT_UNKNOWN",
                "dispatched attempt exists but accepted evidence is unavailable",
                ErrorCode.RESULT_UNKNOWN,
            )
        try:
            self.store.complete_outbox(
                item,
                executor_ref=delivery.executor_ref,
                observations=delivery.observations,
            )
        except FormalTaskViolation as error:
            self.store.release_outbox(item, str(error))
            raise FormalTaskViolation(
                error.reason,
                f"Executor delivery exists but Core rejected its evidence: {error}",
                ErrorCode.RESULT_UNKNOWN,
            ) from error
        return True

    async def drain_outbox(self, *, worker_id: str | None = None) -> int:
        delivered = 0
        worker = worker_id or f"task-core-{uuid.uuid4().hex}"
        while await self.drain_outbox_once(worker_id=worker):
            delivered += 1
        return delivered

    async def reconcile(self) -> dict[str, int]:
        """Resolve only original attempts; never creates a replacement attempt."""

        claimed_before = (
            (datetime.now(UTC) - _OUTBOX_CLAIM_LEASE).isoformat().replace("+00:00", "Z")
        )
        reset_claims = self.store.reset_expired_outbox_claims(
            claimed_before=claimed_before
        )
        delivered = delivery_unavailable = 0
        while True:
            try:
                changed = await self.drain_outbox_once(worker_id="task-core-restart")
            except Exception:  # noqa: BLE001 -- one delivery cannot abort restart audit
                delivery_unavailable += 1
                break
            if not changed:
                break
            delivered += 1
        known = unavailable = lost = 0
        for task, attempt in self.store.nonterminal_attempts():
            if attempt.executor_ref is None:
                self.store.mark_reconciliation_pending(
                    task.task_id, "ATTEMPT_NOT_YET_BOUND"
                )
                unavailable += 1
                continue
            self.store.mark_reconciliation_pending(
                task.task_id, "EXECUTOR_STATUS_QUERY", in_progress=True
            )
            try:
                resolution = await self.executor.status(task, attempt)
            except Exception as error:  # noqa: BLE001 -- isolate one Executor attempt
                self.store.mark_reconciliation_pending(
                    task.task_id,
                    f"EXECUTOR_STATUS_ERROR: {error}"[:1000],
                )
                unavailable += 1
                continue
            if isinstance(resolution, ExecutorDeliveryResult):
                if resolution.executor_ref != attempt.executor_ref:
                    self.store.mark_reconciliation_pending(
                        task.task_id, "EXECUTOR_STATUS_BINDING_MISMATCH"
                    )
                    unavailable += 1
                    continue
                if not resolution.observations:
                    self.store.mark_reconciliation_resolved(
                        task.task_id, "EXECUTOR_STATE_UNCHANGED"
                    )
                    known += 1
                    continue
                observations = resolution.observations
            elif isinstance(resolution, ExecutorObservation):
                observations = (resolution,)
            else:
                self.store.mark_reconciliation_pending(
                    task.task_id, "EXECUTOR_STATUS_PROTOCOL_VIOLATION"
                )
                unavailable += 1
                continue
            final = observations[-1]
            if (
                final.task_id != task.task_id
                or final.attempt_id != attempt.attempt_id
                or final.executor_id != attempt.executor_id
                or final.executor_ref != attempt.executor_ref
            ):
                self.store.mark_reconciliation_pending(
                    task.task_id, "EXECUTOR_STATUS_BINDING_MISMATCH"
                )
                unavailable += 1
                continue
            if final.resolution is ExecutorResolution.KNOWN:
                try:
                    self.store.apply_observations(observations)
                except FormalTaskViolation as error:
                    self.store.mark_reconciliation_pending(
                        task.task_id,
                        f"EXECUTOR_EVIDENCE_REJECTED: {error.reason}",
                    )
                    unavailable += 1
                else:
                    known += 1
                    await self._publish_reconciliation_events(
                        task, after_seq=task.event_head
                    )
            elif final.resolution is ExecutorResolution.LOST:
                self.store.resolve_lost_attempt(
                    task.task_id,
                    attempt.attempt_id,
                    final.error or "EXECUTOR_ATTEMPT_LOST",
                )
                lost += 1
                await self._publish_reconciliation_events(
                    task, after_seq=task.event_head
                )
            else:
                self.store.mark_reconciliation_pending(
                    task.task_id, final.error or "EXECUTOR_STATUS_UNAVAILABLE"
                )
                unavailable += 1
        return {
            "reset_claims": reset_claims,
            "delivered": delivered,
            "delivery_unavailable": delivery_unavailable,
            "known": known,
            "unavailable": unavailable,
            "lost": lost,
        }


__all__ = [
    "FormalExecutor",
    "PersistentTaskCore",
    "ReconciliationEventSink",
    "project_task_event",
]
