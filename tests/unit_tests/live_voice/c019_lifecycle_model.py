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


class NextPreparationState(StrEnum):
    """Browser one-ahead preparation of the unit after the buffered successor."""

    NONE = "none"
    IN_FLIGHT = "in_flight"
    FENCED = "fenced"
    SETTLED = "settled"


class FailureCleanupSource(StrEnum):
    NONE = "none"
    FENCED = "fenced"
    EXTERNAL = "external"


class InterruptingCaptureState(StrEnum):
    """Browser successor capture opened during playout of the response."""

    NONE = "none"
    LIVE = "live"
    END_OF_TURN = "end_of_turn"
    REVOKED = "revoked"
    RELEASED = "released"


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
    SUCCESSOR_CAPTURE_READY = "successor_capture_ready"
    SPOKEN_BARGE_IN = "spoken_barge_in"
    STOP_REQUESTED = "stop_requested"
    EXIT_REQUESTED = "exit_requested"
    CAPTURE_AUTHORITY_REVOKED = "capture_authority_revoked"
    CAPTURE_END_OF_TURN = "capture_end_of_turn"
    UNIFIED_SUBMIT = "unified_submit"
    FENCED_RESPONSE_EFFECT = "fenced_response_effect"
    CONTINUATION_SETTLEMENT_DEADLINE = "continuation_settlement_deadline"
    ACTIVE_UNIT_PLAYOUT = "active_unit_playout"
    SUCCESSOR_BUFFERED = "successor_buffered"
    NEXT_PREPARATION_STARTED = "next_preparation_started"
    PREPARATION_CANCEL_SIGNAL = "preparation_cancel_signal"
    PREPARATION_PROVIDER_REJECTED = "preparation_provider_rejected"
    STAGED_LOCAL_CLOSE = "staged_local_close"
    BARGE_HANDLER_SETTLED = "barge_handler_settled"
    PREPARATION_SETTLED_CANCELLED = "preparation_settled_cancelled"
    FENCED_CALLBACK_FAILURE_CLEANUP = "fenced_callback_failure_cleanup"
    EXTERNAL_FAILURE_CLEANUP = "external_failure_cleanup"
    FENCED_UNIT_DELIVERED = "fenced_unit_delivered"
    FENCED_UNIT_DISCARDED = "fenced_unit_discarded"
    FENCED_UNIT_ADOPTED = "fenced_unit_adopted"
    OWNED_CONTINUATION_CLEANUP_STARTED = "owned_continuation_cleanup_started"
    CAPTURE_FRAME_ACCEPTED = "capture_frame_accepted"
    CAPTURE_FRAME_DROPPED_DURING_OWNED_CLEANUP = (
        "capture_frame_dropped_during_owned_cleanup"
    )
    OWNED_CONTINUATION_CLEANUP_SETTLED = "owned_continuation_cleanup_settled"


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
    ordinary_deadline_ms: int | None = None
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
    interrupting_capture: InterruptingCaptureState = InterruptingCaptureState.NONE
    spoken_barge_fenced: bool = False
    local_stop_requested: bool = False
    committed_submits_after_fence: int = 0
    fenced_response_effects: int = 0
    continuation_settled: bool = False
    active_unit_playing: bool = False
    buffered_successor: bool = False
    next_preparation: NextPreparationState = NextPreparationState.NONE
    preparation_cancel_signalled: bool = False
    preparation_provider_rejected: bool = False
    staged_locally_closed: bool = False
    barge_handler_settled: bool = False
    fenced_unit_pending: bool = False
    fenced_successor_pending: bool = False
    fenced_preparation_pending: bool = False
    failure_cleanup: FailureCleanupSource = FailureCleanupSource.NONE
    fenced_unit_delivered: bool = False
    owned_continuation_cleanup_pending: bool = False
    owned_continuation_cleanup_settled: bool = False
    capture_source_next_seq: int = 0
    capture_owner_retained_next_seq: int = 0


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
    fence_admitted = not state.spoken_barge_fenced and not state.local_stop_requested
    if (
        state.interrupting_capture is InterruptingCaptureState.NONE
        and state.outcome is OutcomeState.ACTIVE
    ):
        events.append(LifecycleEvent.SUCCESSOR_CAPTURE_READY)
    if (
        state.interrupting_capture is InterruptingCaptureState.LIVE
        and state.outcome in {OutcomeState.ACTIVE, OutcomeState.SUCCEEDED}
        and fence_admitted
    ):
        events.append(LifecycleEvent.SPOKEN_BARGE_IN)
    if (
        state.outcome in {OutcomeState.ACTIVE, OutcomeState.SUCCEEDED}
        and fence_admitted
    ):
        events.append(LifecycleEvent.STOP_REQUESTED)
        events.append(LifecycleEvent.EXIT_REQUESTED)
    if state.interrupting_capture in {
        InterruptingCaptureState.LIVE,
        InterruptingCaptureState.END_OF_TURN,
    }:
        events.append(LifecycleEvent.CAPTURE_AUTHORITY_REVOKED)
    if state.interrupting_capture is InterruptingCaptureState.LIVE:
        events.append(LifecycleEvent.CAPTURE_END_OF_TURN)
    if state.interrupting_capture is InterruptingCaptureState.END_OF_TURN:
        events.append(LifecycleEvent.UNIFIED_SUBMIT)
    if state.spoken_barge_fenced or state.local_stop_requested:
        events.append(LifecycleEvent.FENCED_RESPONSE_EFFECT)
        if not state.continuation_settled:
            events.append(LifecycleEvent.CONTINUATION_SETTLEMENT_DEADLINE)
    fenced = state.spoken_barge_fenced or state.local_stop_requested
    if state.outcome is OutcomeState.ACTIVE and not state.active_unit_playing:
        events.append(LifecycleEvent.ACTIVE_UNIT_PLAYOUT)
    if state.active_unit_playing and not state.buffered_successor:
        events.append(LifecycleEvent.SUCCESSOR_BUFFERED)
    if (
        state.buffered_successor
        and state.next_preparation is NextPreparationState.NONE
        and not fenced
    ):
        events.append(LifecycleEvent.NEXT_PREPARATION_STARTED)
    if state.next_preparation in {
        NextPreparationState.IN_FLIGHT,
        NextPreparationState.FENCED,
    }:
        if not state.preparation_cancel_signalled and fenced:
            events.append(LifecycleEvent.PREPARATION_CANCEL_SIGNAL)
        if not state.preparation_provider_rejected:
            events.append(LifecycleEvent.PREPARATION_PROVIDER_REJECTED)
    if state.fenced_preparation_pending and (
        state.preparation_cancel_signalled or state.preparation_provider_rejected
    ):
        events.append(LifecycleEvent.PREPARATION_SETTLED_CANCELLED)
    if state.fenced_successor_pending:
        events.append(LifecycleEvent.STAGED_LOCAL_CLOSE)
    if state.fenced_unit_pending:
        events.append(LifecycleEvent.BARGE_HANDLER_SETTLED)
    if fenced_callbacks_pending(state) > 0:
        events.append(LifecycleEvent.FENCED_CALLBACK_FAILURE_CLEANUP)
    if state.failure_cleanup is FailureCleanupSource.NONE:
        events.append(LifecycleEvent.EXTERNAL_FAILURE_CLEANUP)
    if fenced and not state.fenced_unit_delivered:
        events.append(LifecycleEvent.FENCED_UNIT_DELIVERED)
    if state.fenced_unit_delivered:
        events.append(LifecycleEvent.FENCED_UNIT_DISCARDED)
        events.append(LifecycleEvent.FENCED_UNIT_ADOPTED)
    if (
        state.spoken_barge_fenced
        and state.interrupting_capture is InterruptingCaptureState.LIVE
        and not state.owned_continuation_cleanup_pending
        and not state.owned_continuation_cleanup_settled
    ):
        events.append(LifecycleEvent.OWNED_CONTINUATION_CLEANUP_STARTED)
    if state.interrupting_capture is InterruptingCaptureState.LIVE:
        events.append(LifecycleEvent.CAPTURE_FRAME_ACCEPTED)
    if (
        state.owned_continuation_cleanup_pending
        and state.interrupting_capture is InterruptingCaptureState.LIVE
    ):
        events.append(LifecycleEvent.CAPTURE_FRAME_DROPPED_DURING_OWNED_CLEANUP)
        events.append(LifecycleEvent.OWNED_CONTINUATION_CLEANUP_SETTLED)
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
            ordinary_deadline_ms=None,
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
            ordinary_deadline_ms=None,
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
            ordinary_deadline_ms=None,
            promotion_deadline_ms=None,
            expected_transport_close=(
                state.expected_transport_close
                or state.transport is TransportState.ATTACHED
            ),
        )
    if event is LifecycleEvent.PAUSE_REQUESTED:
        return replace(
            state,
            control=ControlState.PAUSE_REQUESTED,
            pause_owner=PauseOwner.ORDINARY,
            pause_deadline_kind=PauseDeadlineKind.ORDINARY,
            ordinary_deadline_ms=state.now_ms + 60_000,
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
            ordinary_deadline_ms=None,
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
            ordinary_deadline_ms=None,
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
            ordinary_deadline_ms=None,
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
            ordinary_deadline_ms=None,
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
    if event is LifecycleEvent.SUCCESSOR_CAPTURE_READY:
        return replace(state, interrupting_capture=InterruptingCaptureState.LIVE)
    if event is LifecycleEvent.SPOKEN_BARGE_IN:
        # Real speech on the successor capture fences the response exactly
        # like CANCEL, but the capture that carries the interrupting speech
        # stays authoritative until its own end of turn.
        return replace(
            _fence_continuation(_fence_response(state)),
            spoken_barge_fenced=True,
        )
    if event in {LifecycleEvent.STOP_REQUESTED, LifecycleEvent.EXIT_REQUESTED}:
        return replace(
            _fence_continuation(_fence_response(state)),
            local_stop_requested=True,
            interrupting_capture=(
                InterruptingCaptureState.RELEASED
                if state.interrupting_capture
                in {InterruptingCaptureState.LIVE, InterruptingCaptureState.END_OF_TURN}
                else state.interrupting_capture
            ),
        )
    if event is LifecycleEvent.CAPTURE_AUTHORITY_REVOKED:
        return replace(state, interrupting_capture=InterruptingCaptureState.REVOKED)
    if event is LifecycleEvent.CAPTURE_END_OF_TURN:
        return replace(state, interrupting_capture=InterruptingCaptureState.END_OF_TURN)
    if event is LifecycleEvent.UNIFIED_SUBMIT:
        return replace(
            state,
            interrupting_capture=InterruptingCaptureState.RELEASED,
            committed_submits_after_fence=(
                state.committed_submits_after_fence
                + (1 if state.spoken_barge_fenced or state.local_stop_requested else 0)
            ),
        )
    if event is LifecycleEvent.FENCED_RESPONSE_EFFECT:
        return replace(state, fenced_response_effects=state.fenced_response_effects + 1)
    if event is LifecycleEvent.ACTIVE_UNIT_PLAYOUT:
        return replace(state, active_unit_playing=True)
    if event is LifecycleEvent.SUCCESSOR_BUFFERED:
        return replace(state, buffered_successor=True)
    if event is LifecycleEvent.NEXT_PREPARATION_STARTED:
        return replace(state, next_preparation=NextPreparationState.IN_FLIGHT)
    if event is LifecycleEvent.PREPARATION_CANCEL_SIGNAL:
        return replace(state, preparation_cancel_signalled=True)
    if event is LifecycleEvent.PREPARATION_PROVIDER_REJECTED:
        # A Provider rejection of a fenced preparation is a fenced callback;
        # before any fence it is an independent, still authoritative failure.
        if state.next_preparation is NextPreparationState.FENCED:
            return replace(state, preparation_provider_rejected=True)
        return replace(
            state,
            preparation_provider_rejected=True,
            next_preparation=NextPreparationState.SETTLED,
            failure_cleanup=FailureCleanupSource.EXTERNAL,
        )
    if event is LifecycleEvent.STAGED_LOCAL_CLOSE:
        # The owned local close of the buffered successor settles as a
        # cancellation.
        return replace(
            state, staged_locally_closed=True, fenced_successor_pending=False
        )
    if event is LifecycleEvent.BARGE_HANDLER_SETTLED:
        # The FORMAL_PLAYOUT_BARGED / Stop / Exit handler settles the active
        # unit as a cancellation.
        return replace(state, barge_handler_settled=True, fenced_unit_pending=False)
    if event is LifecycleEvent.PREPARATION_SETTLED_CANCELLED:
        return replace(
            state,
            fenced_preparation_pending=False,
            next_preparation=NextPreparationState.SETTLED,
        )
    if event is LifecycleEvent.FENCED_CALLBACK_FAILURE_CLEANUP:
        # The defect: an error or callback that belongs to a continuation or
        # preparation already fenced by the spoken barge enters failure cleanup
        # instead of settling as an owned cancellation.
        if state.fenced_preparation_pending:
            consumed = {
                "fenced_preparation_pending": False,
                "next_preparation": NextPreparationState.SETTLED,
            }
        elif state.fenced_successor_pending:
            consumed = {"fenced_successor_pending": False}
        else:
            consumed = {"fenced_unit_pending": False}
        return replace(state, failure_cleanup=FailureCleanupSource.FENCED, **consumed)
    if event is LifecycleEvent.EXTERNAL_FAILURE_CLEANUP:
        return replace(state, failure_cleanup=FailureCleanupSource.EXTERNAL)
    if event is LifecycleEvent.FENCED_UNIT_DELIVERED:
        # The Gateway still delivers a later audio unit of the fenced response
        # through the notification lane after the fence.
        return replace(state, fenced_unit_delivered=True)
    if event is LifecycleEvent.FENCED_UNIT_DISCARDED:
        return replace(state, fenced_unit_delivered=False)
    if event is LifecycleEvent.FENCED_UNIT_ADOPTED:
        # The defect: the fenced unit is adopted as a new continuation, which
        # can only fail (sequence gap) or replay fenced audio.
        return replace(
            state,
            fenced_unit_delivered=False,
            fenced_response_effects=state.fenced_response_effects + 1,
        )
    if event is LifecycleEvent.OWNED_CONTINUATION_CLEANUP_STARTED:
        return replace(state, owned_continuation_cleanup_pending=True)
    if event is LifecycleEvent.CAPTURE_FRAME_ACCEPTED:
        return replace(
            state,
            capture_source_next_seq=state.capture_source_next_seq + 1,
            capture_owner_retained_next_seq=state.capture_owner_retained_next_seq + 1,
        )
    if event is LifecycleEvent.CAPTURE_FRAME_DROPPED_DURING_OWNED_CLEANUP:
        return replace(
            state,
            capture_source_next_seq=state.capture_source_next_seq + 1,
        )
    if event is LifecycleEvent.OWNED_CONTINUATION_CLEANUP_SETTLED:
        return replace(
            state,
            owned_continuation_cleanup_pending=False,
            owned_continuation_cleanup_settled=True,
        )
    if event is LifecycleEvent.CONTINUATION_SETTLEMENT_DEADLINE:
        # The bounded settlement window after a fence has elapsed: an end of
        # turn observed on the interrupting capture must have produced its one
        # committed submit by now.
        return replace(state, continuation_settled=True)
    raise AssertionError(f"unhandled lifecycle event: {event}")


def _fence_continuation(state: LifecycleState) -> LifecycleState:
    """Fence the active unit, the buffered successor and the next preparation.

    Every callback still owned by them (staged local close, Provider
    rejection, cancel signal, transition ACK) becomes a fenced callback that
    must settle as an owned cancellation.
    """

    next_preparation = state.next_preparation
    fenced_preparation = state.fenced_preparation_pending
    if next_preparation is NextPreparationState.IN_FLIGHT:
        next_preparation = NextPreparationState.FENCED
        fenced_preparation = True
    return replace(
        state,
        active_unit_playing=False,
        fenced_unit_pending=state.fenced_unit_pending or state.active_unit_playing,
        fenced_successor_pending=(
            state.fenced_successor_pending or state.buffered_successor
        ),
        fenced_preparation_pending=fenced_preparation,
        next_preparation=next_preparation,
    )


def fenced_callbacks_pending(state: LifecycleState) -> int:
    """Callbacks still owned by the fenced continuation or preparation."""

    return sum(
        (
            state.fenced_unit_pending,
            state.fenced_successor_pending,
            state.fenced_preparation_pending,
        )
    )


def _fence_response(state: LifecycleState) -> LifecycleState:
    """Cancel the response: Provider, reader, pause owners, successor."""

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
        ordinary_deadline_ms=None,
        promotion_deadline_ms=None,
        expected_transport_close=(
            state.expected_transport_close or state.transport is TransportState.ATTACHED
        ),
    )


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
    if (
        state.ordinary_deadline_ms is not None
        and state.pause_owner is not PauseOwner.ORDINARY
    ):
        found.append("C019-ORDINARY-DEADLINE-01")
    if state.foreign_control_rejected and state.authority_effects_after_foreign:
        found.append("C019-IDENTITY-01")
    if state.failure_cleanup is FailureCleanupSource.FENCED:
        found.append("C019-FENCED-CALLBACK-01")
    if (
        state.spoken_barge_fenced
        and state.failure_cleanup is not FailureCleanupSource.EXTERNAL
        and state.capture_source_next_seq != state.capture_owner_retained_next_seq
    ):
        found.append("C019-CAPTURE-SEQUENCE-CONTINUITY-01")
    if (
        state.spoken_barge_fenced
        and (
            (
                state.interrupting_capture is InterruptingCaptureState.REVOKED
                and state.failure_cleanup is not FailureCleanupSource.EXTERNAL
            )
            or state.committed_submits_after_fence > 1
            or state.fenced_response_effects > 0
            or (
                state.continuation_settled
                and state.interrupting_capture is InterruptingCaptureState.END_OF_TURN
            )
        )
    ) or (
        state.local_stop_requested
        and (
            state.committed_submits_after_fence > 0 or state.fenced_response_effects > 0
        )
    ):
        found.append("C019-SPOKEN-BARGE-CONTINUATION-01")
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


def with_spoken_barge_observation(
    state: LifecycleState,
    *,
    fence: str,
    interrupting_capture: str,
    committed_submits_after_fence: int,
    fenced_response_effects: int,
    settled: bool = False,
    failure_cleanup: str = "none",
) -> LifecycleState:
    """Translate observed Browser/Gateway facts after a playout fence.

    ``fence`` is ``"spoken_barge"`` (real speech during playout), ``"stop"``,
    ``"exit"`` or ``"none"``. ``interrupting_capture`` is the observed state of
    the successor capture that carried the interrupting speech: ``"live"``,
    ``"end_of_turn"``, ``"revoked"`` (its media authority was revoked or its
    streaming recognition was aborted before an end of turn), ``"released"``
    or ``"none"``. ``settled`` records that the bounded settlement window after
    the fence has elapsed in the observed run. ``failure_cleanup`` is
    ``"none"``, ``"fenced"`` (Product P1 entered failure cleanup from an error
    or callback owned by the fenced continuation or preparation) or
    ``"external"`` (an independent, still authoritative Provider or transport
    failure).
    """

    if fence not in {"spoken_barge", "stop", "exit", "none"}:
        raise ValueError("fence must be spoken_barge, stop, exit or none")
    if committed_submits_after_fence < 0 or fenced_response_effects < 0:
        raise ValueError("observed counts cannot be negative")
    return replace(
        state,
        spoken_barge_fenced=fence == "spoken_barge",
        local_stop_requested=fence in {"stop", "exit"},
        interrupting_capture=InterruptingCaptureState(interrupting_capture),
        committed_submits_after_fence=committed_submits_after_fence,
        fenced_response_effects=fenced_response_effects,
        continuation_settled=settled,
        failure_cleanup=FailureCleanupSource(failure_cleanup),
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
