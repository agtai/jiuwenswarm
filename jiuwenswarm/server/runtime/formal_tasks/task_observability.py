"""Host task projections into the shared, privacy-filtered telemetry contract."""
from __future__ import annotations
from jiuwenswarm.common.telemetry.observability import (
    RouteDescriptor, LiveVoiceObservation, OBSERVED_STATES,
    OBSERVABILITY_SCHEMA_VERSION, _violation, create_observation,
)

def observation_from_task_event(
    event: object,
    *,
    observation_id: str,
    observed_at: str,
    monotonic_ms: float,
    route: RouteDescriptor | object,
) -> LiveVoiceObservation:
    """Project a public PersistentTaskEvent without copying its free-text details."""

    from jiuwenswarm.server.runtime.formal_tasks.formal_task_models import PersistentTaskEvent

    if not isinstance(event, PersistentTaskEvent):
        raise _violation("INVALID_TASK_EVENT", "event must be PersistentTaskEvent")
    state = event.state if event.state in OBSERVED_STATES else None
    if state is None:
        raise _violation("INVALID_VOCABULARY", "task event state is not observable")
    outcome = event.outcome
    reason_code = None
    if state == "terminal" and outcome == "failed":
        reason_code = "TASK_FAILURE"
    elif state == "terminal" and outcome == "cancelled":
        reason_code = "CANCEL_TERMINAL"
    return create_observation(
        {
            "schema_version": OBSERVABILITY_SCHEMA_VERSION,
            "event_id": observation_id,
            "event_name": "task.state_observed",
            "segment_name": "task.progress",
            "observed_at": observed_at,
            "monotonic_ms": monotonic_ms,
            "binding": {
                "correlation_id": event.correlation_id,
                "task_id": event.task_id,
                "attempt_id": event.attempt_id,
            },
            "route": route.to_dict() if isinstance(route, RouteDescriptor) else route,
            "source_component": "task.core",
            "source_event_id": event.event_id,
            "source_occurred_at": event.occurred_at,
            "source_seq": event.seq,
            "state": state,
            "outcome": outcome,
            "reason_code": reason_code,
        }
    )


def observation_from_task_outbox(
    item: object,
    task: object,
    *,
    observation_id: str,
    observed_at: str,
    monotonic_ms: float,
    route: RouteDescriptor | object,
) -> LiveVoiceObservation:
    """Observe a durable outbox item without copying its task spec or instruction."""

    from jiuwenswarm.server.runtime.formal_tasks.formal_task_models import (
        OutboxKind,
        OutboxState,
        PersistentOutboxItem,
        PersistentTaskRecord,
    )

    if not isinstance(item, PersistentOutboxItem) or not isinstance(
        task, PersistentTaskRecord
    ):
        raise _violation(
            "INVALID_TASK_OUTBOX", "item and task must use formal persistent models"
        )
    if not isinstance(item.kind, OutboxKind) or not isinstance(item.state, OutboxState):
        raise _violation(
            "INVALID_TASK_OUTBOX", "outbox kind and state must use formal vocabulary"
        )
    if (
        item.task_id != task.task_id
        or item.attempt_id != task.attempt_id
        or item.scope != task.scope
    ):
        raise _violation(
            "TASK_OUTBOX_BINDING_MISMATCH",
            "outbox item must bind the exact task, attempt, and scope",
        )
    event_name = {
        OutboxKind.ATTEMPT_DISPATCH: "task.dispatch_outbox_observed",
        OutboxKind.ATTEMPT_CANCEL: "task.cancel_outbox_observed",
        OutboxKind.ATTEMPT_ADJUST: "task.adjust_outbox_observed",
    }[item.kind]
    return create_observation(
        {
            "schema_version": OBSERVABILITY_SCHEMA_VERSION,
            "event_id": observation_id,
            "event_name": event_name,
            "segment_name": "task.queue",
            "observed_at": observed_at,
            "monotonic_ms": monotonic_ms,
            "binding": {
                "correlation_id": task.correlation_id,
                "task_id": task.task_id,
                "attempt_id": task.attempt_id,
            },
            "route": route.to_dict() if isinstance(route, RouteDescriptor) else route,
            "source_component": "task.core",
            "source_record_id": item.outbox_id,
            "source_seq": item.source_seq,
            "state": item.state.value,
        }
    )
