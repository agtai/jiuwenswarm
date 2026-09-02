"""Executable safety oracle for the bounded C019 continuation lifecycle."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from enum import StrEnum


class ProviderState(StrEnum):
    ACTIVE = "active"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OutcomeState(StrEnum):
    ACTIVE = "active"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReaderState(StrEnum):
    RUNNING = "running"
    EXITED = "exited"


class ControlState(StrEnum):
    ACTIVE = "active"
    PAUSE_REQUESTED = "pause_requested"
    PAUSED = "paused"
    RESUME_REQUESTED = "resume_requested"
    PARKED = "parked"


class PauseOwner(StrEnum):
    NONE = "none"
    ORDINARY = "ordinary"
    PARKED = "parked"


class PauseDeadlineKind(StrEnum):
    NONE = "none"
    ORDINARY = "ordinary"
    PARKED = "parked"


class SuccessorState(StrEnum):
    NONE = "none"
    PREFETCHING = "prefetching"
    PARKED = "parked"
    PROMOTED = "promoted"
    PLAYING = "playing"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DownstreamState(StrEnum):
    AVAILABLE = "available"
    FULL = "full"
    DRAINING = "draining"
    EMPTY = "empty"


class TransportState(StrEnum):
    DETACHED = "detached"
    ATTACHED = "attached"
    CLOSED = "closed"


class LifecycleEvent(StrEnum):
    PROVIDER_EVENT_WAIT_STARTED = "provider_event_wait_started"
    PROVIDER_EVENT_DELIVERED = "provider_event_delivered"
    PROVIDER_EVENT_TIMEOUT = "provider_event_timeout"
    PROVIDER_EVENT_SETTLED_TIMEOUT = "provider_event_settled_timeout"
    PROVIDER_EVENT_OWNER_HARD_TIMEOUT = "provider_event_owner_hard_timeout"
    AUDIO_DELTA = "audio_delta"
    DELIVER_AUDIO = "deliver_audio"
    PROVIDER_DONE = "provider_done"
    PROVIDER_FAILURE = "provider_failure"
    ADAPTER_FAILURE = "adapter_failure"
    COMPLETED_PUBLISHED = "completed_published"
    CANCEL = "cancel"
    PAUSE_REQUESTED = "pause_requested"
    PAUSE_ACKNOWLEDGED = "pause_acknowledged"
    RESUME_REQUESTED = "resume_requested"
    RESUME_ACKNOWLEDGED = "resume_acknowledged"
    SUCCESSOR_PREFETCH = "successor_prefetch"
    BROWSER_PARK_REQUESTED = "browser_park_requested"
    GATEWAY_PARK_ACCEPTED = "gateway_park_accepted"
    ADAPTER_PARK_ACKNOWLEDGED = "adapter_park_acknowledged"
    PREDECESSOR_COMPLETE = "predecessor_complete"
    BROWSER_PROMOTION_REQUESTED = "browser_promotion_requested"
    GATEWAY_PROMOTION_ACCEPTED = "gateway_promotion_accepted"
    ADAPTER_PROMOTION_RESUME_REQUESTED = "adapter_promotion_resume_requested"
    ADAPTER_PROMOTION_RESUME_ACKNOWLEDGED = "adapter_promotion_resume_acknowledged"
    READER_RESUMED_AFTER_PROMOTION = "reader_resumed_after_promotion"
    TERMINAL_NOOP_SETTLED = "terminal_noop_settled"
    ADVANCE_TO_PROMOTION_DEADLINE = "advance_to_promotion_deadline"
    SUCCESSOR_PLAY = "successor_play"
    SUCCESSOR_COMPLETE = "successor_complete"
    QUEUE_FULL = "queue_full"
    QUEUE_AVAILABLE = "queue_available"
    BROWSER_RETAIN_FRAME = "browser_retain_frame"
    WAIT_FOR_PARK = "wait_for_park"
    FOREIGN_CONTROL_REJECTED = "foreign_control_rejected"
    AUTHORITY_EFFECT = "authority_effect"
    TRANSPORT_ATTACH = "transport_attach"
    EXPECTED_TRANSPORT_CLOSE = "expected_transport_close"
    TRANSPORT_CLOSE = "transport_close"
    REPORT_TRANSPORT_FAILURE = "report_transport_failure"


@dataclass(frozen=True, slots=True)
class LifecycleState:
    provider: ProviderState = ProviderState.ACTIVE
    outcome: OutcomeState = OutcomeState.ACTIVE
    reader: ReaderState = ReaderState.RUNNING
    provider_event_wait_pending: bool = False
    provider_event_deadline_suspended: bool = False
    provider_event_timed_out_while_parked: bool = False
    control: ControlState = ControlState.ACTIVE
    pause_owner: PauseOwner = PauseOwner.NONE
    pause_deadline_kind: PauseDeadlineKind = PauseDeadlineKind.NONE
    successor: SuccessorState = SuccessorState.NONE
    downstream: DownstreamState = DownstreamState.AVAILABLE
    transport: TransportState = TransportState.DETACHED
    predecessor_complete: bool = False
    successor_was_promoted: bool = False
    accepted_audio_frames: int = 0
    delivered_audio_frames: int = 0
    gateway_queue_frames: int = 0
    gateway_queue_capacity: int = 8
    browser_reserved_frames: int = 0
    park_target_frames: int = 25
    waiting_for_park: bool = False
    next_park_generation: int = 1
    used_park_generations: frozenset[int] = frozenset()
    park_generation_reused: bool = False
    browser_park_generation: int | None = None
    gateway_park_generation: int | None = None
    adapter_park_generation: int | None = None
    browser_promotion_generation: int | None = None
    gateway_promotion_generation: int | None = None
    adapter_resume_generation: int | None = None
    browser_promotion_requested: bool = False
    gateway_promotion_accepted: bool = False
    adapter_resume_requested: bool = False
    adapter_resume_acknowledged: bool = False
    reader_resumed_after_promotion: bool = False
    terminal_noop_settled: bool = False
    park_started_ms: int | None = None
    pause_deadline_ms: int | None = None
    promotion_deadline_ms: int | None = None
    now_ms: int = 0
    requested_unit_seq: int | None = None
    gateway_expected_unit_seq: int | None = None
    accepted_unit_seq: int | None = None
    completed_published: bool = False
    expected_transport_close: bool = False
    transport_failure_reported: bool = False
    foreign_control_rejected: bool = False
    authority_effects_after_foreign: int = 0


_PENDING_CONTROL_STATES = frozenset(
    {
        ControlState.PAUSE_REQUESTED,
        ControlState.PAUSED,
        ControlState.RESUME_REQUESTED,
        ControlState.PARKED,
    }
)


def applicable_events(state: LifecycleState) -> tuple[LifecycleEvent, ...]:
    """Return only transitions admitted by the intended C019 lifecycle."""

    events: list[LifecycleEvent] = []
    if (
        state.provider is ProviderState.ACTIVE
        and state.reader is ReaderState.RUNNING
        and not state.provider_event_wait_pending
    ):
        events.append(LifecycleEvent.PROVIDER_EVENT_WAIT_STARTED)
    if state.provider_event_wait_pending:
        events.append(LifecycleEvent.PROVIDER_EVENT_DELIVERED)
        events.append(LifecycleEvent.PROVIDER_EVENT_SETTLED_TIMEOUT)
        events.append(LifecycleEvent.PROVIDER_EVENT_OWNER_HARD_TIMEOUT)
        if not state.provider_event_deadline_suspended:
            events.append(LifecycleEvent.PROVIDER_EVENT_TIMEOUT)
    if state.provider is ProviderState.ACTIVE and state.reader is ReaderState.RUNNING:
        events.extend(
            (
                LifecycleEvent.AUDIO_DELTA,
                LifecycleEvent.PROVIDER_DONE,
                LifecycleEvent.PROVIDER_FAILURE,
            )
        )
    if state.delivered_audio_frames < state.accepted_audio_frames:
        events.append(LifecycleEvent.DELIVER_AUDIO)
    if state.provider is ProviderState.DONE and state.outcome is OutcomeState.ACTIVE:
        events.extend(
            (LifecycleEvent.ADAPTER_FAILURE, LifecycleEvent.COMPLETED_PUBLISHED)
        )
    if state.outcome in {OutcomeState.ACTIVE, OutcomeState.SUCCEEDED}:
        events.append(LifecycleEvent.CANCEL)
    if state.provider is ProviderState.ACTIVE:
        if state.control is ControlState.ACTIVE:
            events.append(LifecycleEvent.PAUSE_REQUESTED)
        elif state.control is ControlState.PAUSE_REQUESTED:
            events.append(LifecycleEvent.PAUSE_ACKNOWLEDGED)
        elif state.control is ControlState.PAUSED:
            events.append(LifecycleEvent.RESUME_REQUESTED)
        elif state.control is ControlState.RESUME_REQUESTED:
            events.append(LifecycleEvent.RESUME_ACKNOWLEDGED)
    if state.successor is SuccessorState.NONE:
        events.append(LifecycleEvent.SUCCESSOR_PREFETCH)
    if state.successor is SuccessorState.PREFETCHING:
        if state.browser_park_generation is None:
            events.append(LifecycleEvent.BROWSER_PARK_REQUESTED)
        elif state.gateway_park_generation is None:
            events.append(LifecycleEvent.GATEWAY_PARK_ACCEPTED)
        elif state.adapter_park_generation is None:
            events.append(LifecycleEvent.ADAPTER_PARK_ACKNOWLEDGED)
    if not state.predecessor_complete:
        events.append(LifecycleEvent.PREDECESSOR_COMPLETE)
    if state.successor is SuccessorState.PARKED and state.predecessor_complete:
        if not state.browser_promotion_requested:
            events.append(LifecycleEvent.BROWSER_PROMOTION_REQUESTED)
        elif not state.gateway_promotion_accepted:
            events.append(LifecycleEvent.GATEWAY_PROMOTION_ACCEPTED)
        elif (
            state.provider is ProviderState.ACTIVE
            and state.reader is ReaderState.RUNNING
            and not state.adapter_resume_requested
        ):
            events.append(LifecycleEvent.ADAPTER_PROMOTION_RESUME_REQUESTED)
        elif state.adapter_resume_requested and not state.adapter_resume_acknowledged:
            events.append(LifecycleEvent.ADAPTER_PROMOTION_RESUME_ACKNOWLEDGED)
        elif (
            state.adapter_resume_acknowledged
            and state.provider is ProviderState.ACTIVE
            and state.reader is ReaderState.RUNNING
            and not state.reader_resumed_after_promotion
        ):
            events.append(LifecycleEvent.READER_RESUMED_AFTER_PROMOTION)
        elif (
            state.gateway_promotion_accepted
            and state.provider is not ProviderState.ACTIVE
            and not state.terminal_noop_settled
            and state.outcome not in {OutcomeState.FAILED, OutcomeState.CANCELLED}
        ):
            events.append(LifecycleEvent.TERMINAL_NOOP_SETTLED)
    if (
        state.promotion_deadline_ms is not None
        and state.now_ms < state.promotion_deadline_ms
    ):
        events.append(LifecycleEvent.ADVANCE_TO_PROMOTION_DEADLINE)
    if state.successor is SuccessorState.PROMOTED and state.predecessor_complete:
        events.append(LifecycleEvent.SUCCESSOR_PLAY)
    if state.successor is SuccessorState.PLAYING:
        events.append(LifecycleEvent.SUCCESSOR_COMPLETE)
    if state.downstream is not DownstreamState.FULL:
        events.append(LifecycleEvent.QUEUE_FULL)
    else:
        events.append(LifecycleEvent.QUEUE_AVAILABLE)
    if state.gateway_queue_frames > 0:
        events.append(LifecycleEvent.BROWSER_RETAIN_FRAME)
    if (
        state.successor is SuccessorState.PREFETCHING
        and state.control is ControlState.PAUSED
        and state.downstream is DownstreamState.FULL
    ):
        events.append(LifecycleEvent.WAIT_FOR_PARK)
    if not state.foreign_control_rejected:
        events.append(LifecycleEvent.FOREIGN_CONTROL_REJECTED)
    elif state.authority_effects_after_foreign == 0:
        events.append(LifecycleEvent.AUTHORITY_EFFECT)
    if state.transport is TransportState.DETACHED:
        events.append(LifecycleEvent.TRANSPORT_ATTACH)
    if state.transport is TransportState.ATTACHED:
        if not state.expected_transport_close:
            events.append(LifecycleEvent.EXPECTED_TRANSPORT_CLOSE)
        events.append(LifecycleEvent.TRANSPORT_CLOSE)
    if (
        state.transport is TransportState.CLOSED
        and not state.transport_failure_reported
    ):
        events.append(LifecycleEvent.REPORT_TRANSPORT_FAILURE)
    return tuple(events)


def apply_event(state: LifecycleState, event: LifecycleEvent) -> LifecycleState:
    """Apply one admitted event; invalid calls are rejected, not normalized."""

    if event not in applicable_events(state):
        raise ValueError(f"event {event.value} is not applicable to {state}")
    if event is LifecycleEvent.PROVIDER_EVENT_WAIT_STARTED:
        return replace(state, provider_event_wait_pending=True)
    if event is LifecycleEvent.PROVIDER_EVENT_DELIVERED:
        return replace(state, provider_event_wait_pending=False)
    if event is LifecycleEvent.PROVIDER_EVENT_TIMEOUT:
        return replace(
            state,
            provider_event_wait_pending=False,
        )
    if event is LifecycleEvent.PROVIDER_EVENT_SETTLED_TIMEOUT:
        return replace(state, provider_event_wait_pending=False)
    if event is LifecycleEvent.PROVIDER_EVENT_OWNER_HARD_TIMEOUT:
        return replace(
            state,
            provider_event_wait_pending=False,
            provider_event_timed_out_while_parked=(
                state.provider_event_deadline_suspended
            ),
        )
    if event is LifecycleEvent.AUDIO_DELTA:
        return replace(state, accepted_audio_frames=state.accepted_audio_frames + 1)
    if event is LifecycleEvent.DELIVER_AUDIO:
        delivered = state.delivered_audio_frames + 1
        return replace(
            state,
            delivered_audio_frames=delivered,
            downstream=(
                DownstreamState.EMPTY
                if delivered == state.accepted_audio_frames
                else DownstreamState.DRAINING
            ),
        )
    if event is LifecycleEvent.PROVIDER_DONE:
        return replace(
            state,
            provider=ProviderState.DONE,
            reader=ReaderState.EXITED,
            control=ControlState.ACTIVE,
        )
    if event is LifecycleEvent.PROVIDER_FAILURE:
        return replace(
            state,
            provider=ProviderState.FAILED,
            outcome=OutcomeState.FAILED,
            reader=ReaderState.EXITED,
            control=ControlState.ACTIVE,
            pause_owner=PauseOwner.NONE,
            pause_deadline_kind=PauseDeadlineKind.NONE,
            successor=SuccessorState.FAILED,
            waiting_for_park=False,
            pause_deadline_ms=None,
            promotion_deadline_ms=None,
        )
    if event is LifecycleEvent.ADAPTER_FAILURE:
        return replace(
            state,
            outcome=OutcomeState.FAILED,
            control=ControlState.ACTIVE,
            pause_owner=PauseOwner.NONE,
            pause_deadline_kind=PauseDeadlineKind.NONE,
            successor=SuccessorState.FAILED,
            waiting_for_park=False,
            pause_deadline_ms=None,
            promotion_deadline_ms=None,
        )
    if event is LifecycleEvent.COMPLETED_PUBLISHED:
        return replace(
            state,
            outcome=OutcomeState.SUCCEEDED,
            completed_published=True,
        )
    if event is LifecycleEvent.CANCEL:
        return replace(
            state,
            provider=ProviderState.CANCELLED,
            outcome=OutcomeState.CANCELLED,
            reader=ReaderState.EXITED,
            control=ControlState.ACTIVE,
            pause_owner=PauseOwner.NONE,
            pause_deadline_kind=PauseDeadlineKind.NONE,
            successor=SuccessorState.CANCELLED,
            waiting_for_park=False,
            pause_deadline_ms=None,
            promotion_deadline_ms=None,
        )
    if event is LifecycleEvent.PAUSE_REQUESTED:
        return replace(
            state,
            control=ControlState.PAUSE_REQUESTED,
            pause_owner=PauseOwner.ORDINARY,
            pause_deadline_kind=PauseDeadlineKind.ORDINARY,
            pause_deadline_ms=state.now_ms + 60_000,
        )
    if event is LifecycleEvent.PAUSE_ACKNOWLEDGED:
        return replace(state, control=ControlState.PAUSED)
    if event is LifecycleEvent.RESUME_REQUESTED:
        return replace(state, control=ControlState.RESUME_REQUESTED)
    if event is LifecycleEvent.RESUME_ACKNOWLEDGED:
        return replace(
            state,
            control=ControlState.ACTIVE,
            pause_owner=PauseOwner.NONE,
            pause_deadline_kind=PauseDeadlineKind.NONE,
            pause_deadline_ms=None,
        )
    if event is LifecycleEvent.SUCCESSOR_PREFETCH:
        return replace(state, successor=SuccessorState.PREFETCHING)
    if event is LifecycleEvent.BROWSER_PARK_REQUESTED:
        generation = state.next_park_generation
        return replace(
            state,
            browser_park_generation=generation,
            used_park_generations=state.used_park_generations | {generation},
            park_generation_reused=(generation in state.used_park_generations),
        )
    if event is LifecycleEvent.GATEWAY_PARK_ACCEPTED:
        return replace(
            state,
            gateway_park_generation=state.browser_park_generation,
            provider_event_deadline_suspended=state.provider_event_wait_pending,
        )
    if event is LifecycleEvent.ADAPTER_PARK_ACKNOWLEDGED:
        return replace(
            state,
            successor=SuccessorState.PARKED,
            control=ControlState.PARKED,
            pause_owner=PauseOwner.PARKED,
            pause_deadline_kind=PauseDeadlineKind.PARKED,
            adapter_park_generation=state.gateway_park_generation,
            park_started_ms=state.now_ms,
            pause_deadline_ms=state.now_ms + 185_000,
            promotion_deadline_ms=state.now_ms + 180_000,
            waiting_for_park=False,
        )
    if event is LifecycleEvent.PREDECESSOR_COMPLETE:
        return replace(state, predecessor_complete=True)
    if event is LifecycleEvent.BROWSER_PROMOTION_REQUESTED:
        return replace(
            state,
            browser_promotion_requested=True,
            browser_promotion_generation=state.browser_park_generation,
        )
    if event is LifecycleEvent.GATEWAY_PROMOTION_ACCEPTED:
        return replace(
            state,
            gateway_promotion_accepted=True,
            gateway_promotion_generation=state.browser_promotion_generation,
        )
    if event is LifecycleEvent.ADAPTER_PROMOTION_RESUME_REQUESTED:
        return replace(
            state,
            adapter_resume_requested=True,
            adapter_resume_generation=state.gateway_promotion_generation,
        )
    if event is LifecycleEvent.ADAPTER_PROMOTION_RESUME_ACKNOWLEDGED:
        return replace(
            state,
            adapter_resume_acknowledged=True,
            provider_event_deadline_suspended=False,
        )
    if event is LifecycleEvent.READER_RESUMED_AFTER_PROMOTION:
        return replace(
            state,
            successor=SuccessorState.PROMOTED,
            successor_was_promoted=True,
            control=ControlState.ACTIVE,
            reader_resumed_after_promotion=True,
            pause_owner=PauseOwner.NONE,
            pause_deadline_kind=PauseDeadlineKind.NONE,
            pause_deadline_ms=None,
        )
    if event is LifecycleEvent.TERMINAL_NOOP_SETTLED:
        return replace(
            state,
            successor=SuccessorState.PROMOTED,
            successor_was_promoted=True,
            control=ControlState.ACTIVE,
            terminal_noop_settled=True,
            pause_owner=PauseOwner.NONE,
            pause_deadline_kind=PauseDeadlineKind.NONE,
            pause_deadline_ms=None,
        )
    if event is LifecycleEvent.ADVANCE_TO_PROMOTION_DEADLINE:
        assert state.promotion_deadline_ms is not None
        return replace(state, now_ms=state.promotion_deadline_ms)
    if event is LifecycleEvent.SUCCESSOR_PLAY:
        return replace(state, successor=SuccessorState.PLAYING)
    if event is LifecycleEvent.SUCCESSOR_COMPLETE:
        return replace(state, successor=SuccessorState.COMPLETE)
    if event is LifecycleEvent.QUEUE_FULL:
        return replace(
            state,
            downstream=DownstreamState.FULL,
            gateway_queue_frames=state.gateway_queue_capacity,
        )
    if event is LifecycleEvent.QUEUE_AVAILABLE:
        return replace(state, downstream=DownstreamState.AVAILABLE)
    if event is LifecycleEvent.BROWSER_RETAIN_FRAME:
        return replace(
            state,
            gateway_queue_frames=state.gateway_queue_frames - 1,
            browser_reserved_frames=state.browser_reserved_frames + 1,
            downstream=DownstreamState.AVAILABLE,
        )
    if event is LifecycleEvent.WAIT_FOR_PARK:
        return replace(state, waiting_for_park=True)
    if event is LifecycleEvent.FOREIGN_CONTROL_REJECTED:
        return replace(state, foreign_control_rejected=True)
    if event is LifecycleEvent.AUTHORITY_EFFECT:
        return replace(
            state,
            authority_effects_after_foreign=state.authority_effects_after_foreign + 1,
        )
    if event is LifecycleEvent.TRANSPORT_ATTACH:
        return replace(state, transport=TransportState.ATTACHED)
    if event is LifecycleEvent.EXPECTED_TRANSPORT_CLOSE:
        return replace(state, expected_transport_close=True)
    if event is LifecycleEvent.TRANSPORT_CLOSE:
        return replace(state, transport=TransportState.CLOSED)
    if event is LifecycleEvent.REPORT_TRANSPORT_FAILURE:
        return replace(state, transport_failure_reported=True)
    raise AssertionError(f"unhandled lifecycle event: {event}")


def violations(state: LifecycleState) -> tuple[str, ...]:
    found: list[str] = []
    if (
        state.reader is ReaderState.EXITED
        and state.control is ControlState.RESUME_REQUESTED
    ):
        found.append("C019-WAIT-01")
    if state.provider_event_timed_out_while_parked or (
        state.provider_event_wait_pending
        and state.gateway_park_generation is not None
        and not state.adapter_resume_acknowledged
        and not state.provider_event_deadline_suspended
    ):
        found.append("C019-PARK-EVENT-WAIT-01")
    if (
        state.provider is not ProviderState.ACTIVE
        and state.control in _PENDING_CONTROL_STATES
    ):
        found.append("C019-TERM-01")
    if state.successor is SuccessorState.PLAYING and (
        not state.predecessor_complete or not state.successor_was_promoted
    ):
        found.append("C019-ORDER-01")
    if (
        state.successor
        in {
            SuccessorState.PROMOTED,
            SuccessorState.PLAYING,
            SuccessorState.COMPLETE,
        }
        and not state.successor_was_promoted
    ):
        found.append("C019-PARK-01")
    if (
        state.outcome is OutcomeState.SUCCEEDED
        and state.transport is TransportState.CLOSED
        and state.delivered_audio_frames != state.accepted_audio_frames
    ):
        found.append("C019-DRAIN-01")
    if (
        state.waiting_for_park
        and state.control is ControlState.PAUSED
        and state.browser_reserved_frames + state.gateway_queue_frames
        < state.park_target_frames
    ):
        found.append("C019-BACKPRESSURE-01")
    if state.outcome is OutcomeState.CANCELLED and (
        state.reader is not ReaderState.EXITED
        or state.control is not ControlState.ACTIVE
    ):
        found.append("C019-CANCEL-01")
    if state.expected_transport_close and state.transport_failure_reported:
        found.append("C019-TRANSPORT-01")
    if state.foreign_control_rejected and state.authority_effects_after_foreign:
        found.append("C019-IDENTITY-01")
    active_resume_chain = (
        state.adapter_resume_requested
        and state.adapter_resume_acknowledged
        and state.reader_resumed_after_promotion
    )
    promotion_settled = active_resume_chain or state.terminal_noop_settled
    if (
        (state.gateway_promotion_accepted and not state.browser_promotion_requested)
        or (state.adapter_resume_requested and not state.gateway_promotion_accepted)
        or (state.adapter_resume_acknowledged and not state.adapter_resume_requested)
        or (
            state.reader_resumed_after_promotion
            and not state.adapter_resume_acknowledged
        )
        or (state.terminal_noop_settled and not state.gateway_promotion_accepted)
        or (
            state.successor
            in {
                SuccessorState.PROMOTED,
                SuccessorState.PLAYING,
                SuccessorState.COMPLETE,
            }
            and not (
                state.browser_promotion_requested
                and state.gateway_promotion_accepted
                and promotion_settled
            )
        )
    ):
        found.append("C019-PROMOTION-01")
    if state.successor is SuccessorState.PARKED and (
        state.pause_owner is not PauseOwner.PARKED
        or state.pause_deadline_kind is not PauseDeadlineKind.PARKED
        or state.park_started_ms is None
        or state.pause_deadline_ms is None
        or state.promotion_deadline_ms is None
        or state.pause_deadline_ms <= state.now_ms
        or state.promotion_deadline_ms <= state.now_ms
        or state.pause_deadline_ms != state.park_started_ms + 185_000
        or state.promotion_deadline_ms != state.park_started_ms + 180_000
        or state.promotion_deadline_ms >= state.pause_deadline_ms
    ):
        found.append("C019-PARK-DEADLINE-01")
    if (
        state.browser_promotion_requested
        and state.promotion_deadline_ms is not None
        and state.now_ms >= state.promotion_deadline_ms
        and not promotion_settled
        and state.outcome is OutcomeState.ACTIVE
    ):
        found.append("C019-POST-PROMOTION-01")
    park_generations = tuple(
        generation
        for generation in (
            state.browser_park_generation,
            state.gateway_park_generation,
            state.adapter_park_generation,
        )
        if generation is not None
    )
    promotion_generations = tuple(
        generation
        for generation in (
            state.browser_promotion_generation,
            state.gateway_promotion_generation,
            state.adapter_resume_generation,
        )
        if generation is not None
    )
    if (
        state.park_generation_reused
        or len(set(park_generations)) > 1
        or len(set(promotion_generations)) > 1
        or (
            state.gateway_park_generation is not None
            and state.browser_park_generation is None
        )
        or (
            state.adapter_park_generation is not None
            and (
                state.browser_park_generation is None
                or state.gateway_park_generation is None
            )
        )
        or (state.successor is SuccessorState.PARKED and len(park_generations) != 3)
        or (
            state.browser_promotion_requested
            and state.browser_promotion_generation is None
        )
        or (
            state.gateway_promotion_accepted
            and state.gateway_promotion_generation is None
        )
        or (state.adapter_resume_requested and state.adapter_resume_generation is None)
        or (
            promotion_settled
            and not state.terminal_noop_settled
            and len(promotion_generations) != 3
        )
        or (
            promotion_generations
            and park_generations
            and promotion_generations[0] != park_generations[0]
        )
    ):
        found.append("C019-GENERATION-01")
    if (
        state.requested_unit_seq is not None
        and state.gateway_expected_unit_seq is not None
        and state.requested_unit_seq != state.gateway_expected_unit_seq
    ) or (
        state.accepted_unit_seq is not None
        and state.requested_unit_seq != state.accepted_unit_seq
    ):
        found.append("C019-UNIT-SEQUENCE-01")
    return tuple(found)


def from_adapter_snapshot(
    *,
    reader_state: str,
    provider_state: str,
    outcome_state: str,
    pause_requested: bool,
    pause_acknowledged: bool,
    resume_signal_set: bool,
    pause_mode: str | None,
    closing: bool = False,
) -> LifecycleState:
    """Translate the real Adapter's content-free snapshot into oracle state."""

    if pause_requested:
        if pause_mode == "parked":
            control = ControlState.PARKED
        elif pause_acknowledged and resume_signal_set:
            control = ControlState.RESUME_REQUESTED
        elif pause_acknowledged:
            control = ControlState.PAUSED
        else:
            control = ControlState.PAUSE_REQUESTED
    else:
        control = ControlState.ACTIVE
    return LifecycleState(
        provider=(
            ProviderState.CANCELLED if closing else ProviderState(provider_state)
        ),
        outcome=OutcomeState.CANCELLED if closing else OutcomeState(outcome_state),
        reader=ReaderState(reader_state),
        control=control,
    )


def with_gateway_snapshot(
    state: LifecycleState,
    *,
    queue_size: int,
    queue_capacity: int,
    browser_reserved_frames: int,
    prefetch_candidate: bool,
    waiting_for_park: bool,
) -> LifecycleState:
    """Bind content-free Gateway/Browser reserve facts to the oracle."""

    return replace(
        state,
        successor=(
            SuccessorState.PREFETCHING if prefetch_candidate else state.successor
        ),
        downstream=(
            DownstreamState.FULL
            if queue_size == queue_capacity
            else DownstreamState.AVAILABLE
        ),
        gateway_queue_frames=queue_size,
        gateway_queue_capacity=queue_capacity,
        browser_reserved_frames=browser_reserved_frames,
        waiting_for_park=waiting_for_park,
    )


def with_delivery_snapshot(
    state: LifecycleState,
    *,
    accepted_audio_frames: int,
    delivered_audio_frames: int,
    completed_published: bool,
) -> LifecycleState:
    if not 0 <= delivered_audio_frames <= accepted_audio_frames:
        raise ValueError("delivered audio must be within the accepted frame count")
    return replace(
        state,
        outcome=(OutcomeState.SUCCEEDED if completed_published else state.outcome),
        accepted_audio_frames=accepted_audio_frames,
        delivered_audio_frames=delivered_audio_frames,
        completed_published=completed_published,
    )


def with_unit_sequence_observation(
    state: LifecycleState,
    *,
    requested_unit_seq: int,
    gateway_expected_unit_seq: int,
    accepted_unit_seq: int | None,
) -> LifecycleState:
    if min(requested_unit_seq, gateway_expected_unit_seq) < 0:
        raise ValueError("unit sequence must be non-negative")
    if accepted_unit_seq is not None and accepted_unit_seq < 0:
        raise ValueError("accepted unit sequence must be non-negative")
    return replace(
        state,
        requested_unit_seq=requested_unit_seq,
        gateway_expected_unit_seq=gateway_expected_unit_seq,
        accepted_unit_seq=accepted_unit_seq,
    )


def with_transport_observation(
    state: LifecycleState,
    *,
    attached: bool,
    closed: bool,
    expected_close: bool,
    failure_reported: bool,
) -> LifecycleState:
    transport = (
        TransportState.CLOSED
        if closed
        else TransportState.ATTACHED
        if attached
        else TransportState.DETACHED
    )
    return replace(
        state,
        transport=transport,
        expected_transport_close=expected_close,
        transport_failure_reported=failure_reported,
    )


def with_identity_observation(
    state: LifecycleState,
    *,
    rejected_foreign_control: bool,
    authority_effects_before: int,
    authority_effects_after: int,
) -> LifecycleState:
    if authority_effects_after < authority_effects_before:
        raise ValueError("authority effects cannot decrease")
    return replace(
        state,
        foreign_control_rejected=rejected_foreign_control,
        authority_effects_after_foreign=(
            authority_effects_after - authority_effects_before
        ),
    )


def explore(
    initial: LifecycleState,
    *,
    max_depth: int,
) -> dict[str, tuple[LifecycleEvent, ...]]:
    """Return shortest violations reachable through applicable transitions."""

    if max_depth < 0:
        raise ValueError("max_depth must be non-negative")
    pending = deque([(initial, ())])
    seen: dict[LifecycleState, int] = {initial: 0}
    traces: dict[str, tuple[LifecycleEvent, ...]] = {}
    while pending:
        state, trace = pending.popleft()
        for invariant_id in violations(state):
            traces.setdefault(invariant_id, trace)
        if len(trace) >= max_depth:
            continue
        for event in applicable_events(state):
            next_state = apply_event(state, event)
            next_trace = (*trace, event)
            previous_depth = seen.get(next_state)
            if previous_depth is not None and previous_depth <= len(next_trace):
                continue
            seen[next_state] = len(next_trace)
            pending.append((next_state, next_trace))
    return traces
