# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from dataclasses import replace

import pytest

from tests.unit_tests.live_voice.c019_lifecycle_model import (
    ControlState,
    LifecycleEvent,
    LifecycleState,
    PauseDeadlineKind,
    PauseOwner,
    OutcomeState,
    ProviderState,
    ReaderState,
    SuccessorState,
    TransportState,
    applicable_events,
    apply_event,
    explore,
    from_adapter_snapshot,
    violations,
    with_identity_observation,
    with_unit_sequence_observation,
)


def parked_promotion_state() -> LifecycleState:
    state = LifecycleState(next_park_generation=3)
    for event in (
        LifecycleEvent.SUCCESSOR_PREFETCH,
        LifecycleEvent.BROWSER_PARK_REQUESTED,
        LifecycleEvent.GATEWAY_PARK_ACCEPTED,
        LifecycleEvent.ADAPTER_PARK_ACKNOWLEDGED,
        LifecycleEvent.PREDECESSOR_COMPLETE,
        LifecycleEvent.BROWSER_PROMOTION_REQUESTED,
        LifecycleEvent.GATEWAY_PROMOTION_ACCEPTED,
    ):
        state = apply_event(state, event)
    return state


def test_dead_reader_cannot_own_resume_waiter() -> None:
    state = LifecycleState(
        provider=ProviderState.DONE,
        reader=ReaderState.EXITED,
        control=ControlState.RESUME_REQUESTED,
    )

    assert violations(state) == ("C019-WAIT-01", "C019-TERM-01")


def test_successor_cannot_play_before_predecessor_completes() -> None:
    state = LifecycleState(
        successor=SuccessorState.PLAYING,
        successor_was_promoted=True,
        predecessor_complete=False,
        browser_promotion_requested=True,
        gateway_promotion_accepted=True,
        adapter_resume_requested=True,
        adapter_resume_acknowledged=True,
        reader_resumed_after_promotion=True,
        browser_promotion_generation=1,
        gateway_promotion_generation=1,
        adapter_resume_generation=1,
    )

    assert violations(state) == ("C019-ORDER-01",)


def test_cancelled_stream_makes_late_audio_inapplicable() -> None:
    state = apply_event(LifecycleState(), LifecycleEvent.CANCEL)

    assert LifecycleEvent.AUDIO_DELTA not in applicable_events(state)
    with pytest.raises(ValueError, match="audio_delta is not applicable"):
        apply_event(state, LifecycleEvent.AUDIO_DELTA)
    assert violations(state) == ()


def test_explorer_uses_only_applicable_transitions() -> None:
    assert explore(LifecycleState(), max_depth=1) == {}


def test_ordered_park_promotion_playout_trace_is_valid() -> None:
    state = LifecycleState()
    for event in (
        LifecycleEvent.SUCCESSOR_PREFETCH,
        LifecycleEvent.BROWSER_PARK_REQUESTED,
        LifecycleEvent.GATEWAY_PARK_ACCEPTED,
        LifecycleEvent.ADAPTER_PARK_ACKNOWLEDGED,
        LifecycleEvent.PREDECESSOR_COMPLETE,
        LifecycleEvent.BROWSER_PROMOTION_REQUESTED,
        LifecycleEvent.GATEWAY_PROMOTION_ACCEPTED,
        LifecycleEvent.ADAPTER_PROMOTION_RESUME_REQUESTED,
        LifecycleEvent.ADAPTER_PROMOTION_RESUME_ACKNOWLEDGED,
        LifecycleEvent.READER_RESUMED_AFTER_PROMOTION,
        LifecycleEvent.SUCCESSOR_PLAY,
    ):
        state = apply_event(state, event)

    assert violations(state) == ()


def test_park_suspends_the_same_pending_provider_event_wait_until_promotion() -> None:
    state = apply_event(LifecycleState(), LifecycleEvent.PROVIDER_EVENT_WAIT_STARTED)
    for event in (
        LifecycleEvent.SUCCESSOR_PREFETCH,
        LifecycleEvent.BROWSER_PARK_REQUESTED,
        LifecycleEvent.GATEWAY_PARK_ACCEPTED,
        LifecycleEvent.ADAPTER_PARK_ACKNOWLEDGED,
    ):
        state = apply_event(state, event)

    assert state.provider_event_wait_pending is True
    assert state.provider_event_deadline_suspended is True
    assert LifecycleEvent.PROVIDER_EVENT_TIMEOUT not in applicable_events(state)

    for event in (
        LifecycleEvent.PREDECESSOR_COMPLETE,
        LifecycleEvent.BROWSER_PROMOTION_REQUESTED,
        LifecycleEvent.GATEWAY_PROMOTION_ACCEPTED,
        LifecycleEvent.ADAPTER_PROMOTION_RESUME_REQUESTED,
        LifecycleEvent.ADAPTER_PROMOTION_RESUME_ACKNOWLEDGED,
    ):
        state = apply_event(state, event)

    assert state.provider_event_wait_pending is True
    assert state.provider_event_deadline_suspended is False
    state = apply_event(state, LifecycleEvent.PROVIDER_EVENT_DELIVERED)
    assert state.provider_event_wait_pending is False
    assert violations(state) == ()


def test_provider_event_timeout_during_park_violates_wait_ownership() -> None:
    state = apply_event(LifecycleState(), LifecycleEvent.PROVIDER_EVENT_WAIT_STARTED)
    for event in (
        LifecycleEvent.SUCCESSOR_PREFETCH,
        LifecycleEvent.BROWSER_PARK_REQUESTED,
        LifecycleEvent.GATEWAY_PARK_ACCEPTED,
        LifecycleEvent.ADAPTER_PARK_ACKNOWLEDGED,
        LifecycleEvent.PROVIDER_EVENT_OWNER_HARD_TIMEOUT,
    ):
        state = apply_event(state, event)

    assert "C019-PARK-EVENT-WAIT-01" in violations(state)


def test_settled_provider_timeout_can_open_a_new_exact_wait_during_park() -> None:
    state = apply_event(LifecycleState(), LifecycleEvent.PROVIDER_EVENT_WAIT_STARTED)
    for event in (
        LifecycleEvent.SUCCESSOR_PREFETCH,
        LifecycleEvent.BROWSER_PARK_REQUESTED,
        LifecycleEvent.GATEWAY_PARK_ACCEPTED,
        LifecycleEvent.ADAPTER_PARK_ACKNOWLEDGED,
        LifecycleEvent.PROVIDER_EVENT_SETTLED_TIMEOUT,
        LifecycleEvent.PROVIDER_EVENT_WAIT_STARTED,
    ):
        state = apply_event(state, event)

    assert state.provider_event_wait_pending is True
    assert state.provider_event_deadline_suspended is True
    assert violations(state) == ()


def test_explorer_reaches_provider_event_owner_timeout_during_park() -> None:
    traces = explore(LifecycleState(), max_depth=5)

    assert "C019-PARK-EVENT-WAIT-01" in traces


def test_duplicate_successor_promotion_is_inapplicable() -> None:
    state = LifecycleState()
    for event in (
        LifecycleEvent.SUCCESSOR_PREFETCH,
        LifecycleEvent.BROWSER_PARK_REQUESTED,
        LifecycleEvent.GATEWAY_PARK_ACCEPTED,
        LifecycleEvent.ADAPTER_PARK_ACKNOWLEDGED,
        LifecycleEvent.PREDECESSOR_COMPLETE,
        LifecycleEvent.BROWSER_PROMOTION_REQUESTED,
        LifecycleEvent.GATEWAY_PROMOTION_ACCEPTED,
        LifecycleEvent.ADAPTER_PROMOTION_RESUME_REQUESTED,
        LifecycleEvent.ADAPTER_PROMOTION_RESUME_ACKNOWLEDGED,
        LifecycleEvent.READER_RESUMED_AFTER_PROMOTION,
    ):
        state = apply_event(state, event)

    with pytest.raises(
        ValueError, match="browser_promotion_requested is not applicable"
    ):
        apply_event(state, LifecycleEvent.BROWSER_PROMOTION_REQUESTED)


def test_unpromoted_successor_playout_is_inapplicable() -> None:
    state = apply_event(LifecycleState(), LifecycleEvent.SUCCESSOR_PREFETCH)
    state = apply_event(state, LifecycleEvent.PREDECESSOR_COMPLETE)

    with pytest.raises(ValueError, match="successor_play is not applicable"):
        apply_event(state, LifecycleEvent.SUCCESSOR_PLAY)


@pytest.mark.parametrize(
    ("invariant_id", "state"),
    (
        (
            "C019-DRAIN-01",
            LifecycleState(
                outcome=OutcomeState.SUCCEEDED,
                transport=TransportState.CLOSED,
                accepted_audio_frames=2,
                delivered_audio_frames=1,
            ),
        ),
        (
            "C019-BACKPRESSURE-01",
            LifecycleState(
                control=ControlState.PAUSED,
                successor=SuccessorState.PREFETCHING,
                gateway_queue_frames=8,
                browser_reserved_frames=0,
                waiting_for_park=True,
            ),
        ),
        (
            "C019-CANCEL-01",
            LifecycleState(
                provider=ProviderState.CANCELLED,
                outcome=OutcomeState.CANCELLED,
                reader=ReaderState.RUNNING,
            ),
        ),
        (
            "C019-TRANSPORT-01",
            LifecycleState(
                transport=TransportState.CLOSED,
                expected_transport_close=True,
                transport_failure_reported=True,
            ),
        ),
    ),
)
def test_structural_invariants_reject_inconsistent_states(
    invariant_id: str,
    state: LifecycleState,
) -> None:
    assert invariant_id in violations(state)


def test_foreign_rejection_is_valid_until_it_causes_authority_effect() -> None:
    rejected = with_identity_observation(
        LifecycleState(),
        rejected_foreign_control=True,
        authority_effects_before=0,
        authority_effects_after=0,
    )
    leaked = with_identity_observation(
        rejected,
        rejected_foreign_control=True,
        authority_effects_before=0,
        authority_effects_after=1,
    )

    assert violations(rejected) == ()
    assert violations(leaked) == ("C019-IDENTITY-01",)


def test_expected_transport_close_without_failure_report_is_valid() -> None:
    state = apply_event(LifecycleState(), LifecycleEvent.TRANSPORT_ATTACH)
    state = apply_event(state, LifecycleEvent.EXPECTED_TRANSPORT_CLOSE)
    state = apply_event(state, LifecycleEvent.TRANSPORT_CLOSE)

    assert violations(state) == ()


def test_cancel_makes_transport_close_expected_and_rejects_visible_failure() -> None:
    state = apply_event(LifecycleState(), LifecycleEvent.TRANSPORT_ATTACH)
    state = apply_event(state, LifecycleEvent.CANCEL)

    assert state.expected_transport_close is True
    state = apply_event(state, LifecycleEvent.TRANSPORT_CLOSE)
    assert violations(state) == ()

    leaked = apply_event(state, LifecycleEvent.REPORT_TRANSPORT_FAILURE)
    assert violations(leaked) == ("C019-TRANSPORT-01",)


def test_real_adapter_snapshot_translation_rejects_dead_reader_waiter() -> None:
    state = from_adapter_snapshot(
        reader_state="exited",
        provider_state="done",
        outcome_state="active",
        pause_requested=True,
        pause_acknowledged=True,
        resume_signal_set=True,
        pause_mode="ordinary",
    )

    assert violations(state) == ("C019-WAIT-01", "C019-TERM-01")


def test_terminal_noop_snapshot_is_structurally_valid() -> None:
    state = from_adapter_snapshot(
        reader_state="exited",
        provider_state="done",
        outcome_state="active",
        pause_requested=False,
        pause_acknowledged=True,
        resume_signal_set=True,
        pause_mode=None,
    )

    assert violations(state) == ()


def test_browser_promotion_requires_gateway_and_adapter_resume_chain() -> None:
    state = LifecycleState(
        successor=SuccessorState.PROMOTED,
        successor_was_promoted=True,
        predecessor_complete=True,
        browser_promotion_requested=True,
        gateway_promotion_accepted=True,
        adapter_resume_requested=False,
        adapter_resume_acknowledged=False,
        reader_resumed_after_promotion=False,
    )

    assert "C019-PROMOTION-01" in violations(state)


def test_park_adoption_cannot_retain_ordinary_owner_or_deadline() -> None:
    state = LifecycleState(
        successor=SuccessorState.PARKED,
        control=ControlState.PARKED,
        pause_owner=PauseOwner.ORDINARY,
        pause_deadline_kind=PauseDeadlineKind.ORDINARY,
        browser_park_generation=7,
        gateway_park_generation=7,
        adapter_park_generation=7,
    )

    assert "C019-PARK-DEADLINE-01" in violations(state)


def test_park_adoption_releases_the_superseded_ordinary_deadline() -> None:
    state = apply_event(LifecycleState(), LifecycleEvent.PAUSE_REQUESTED)
    assert state.ordinary_deadline_ms == 60_000
    for event in (
        LifecycleEvent.PAUSE_ACKNOWLEDGED,
        LifecycleEvent.SUCCESSOR_PREFETCH,
        LifecycleEvent.BROWSER_PARK_REQUESTED,
        LifecycleEvent.GATEWAY_PARK_ACCEPTED,
        LifecycleEvent.ADAPTER_PARK_ACKNOWLEDGED,
    ):
        state = apply_event(state, event)

    assert state.ordinary_deadline_ms is None
    assert violations(state) == ()

    leaked = replace(state, ordinary_deadline_ms=60_000)
    assert violations(leaked) == ("C019-ORDINARY-DEADLINE-01",)


def test_promotion_deadline_requires_resume_terminal_or_explicit_failure() -> None:
    state = LifecycleState()
    for event in (
        LifecycleEvent.SUCCESSOR_PREFETCH,
        LifecycleEvent.BROWSER_PARK_REQUESTED,
        LifecycleEvent.GATEWAY_PARK_ACCEPTED,
        LifecycleEvent.ADAPTER_PARK_ACKNOWLEDGED,
        LifecycleEvent.PREDECESSOR_COMPLETE,
        LifecycleEvent.BROWSER_PROMOTION_REQUESTED,
        LifecycleEvent.GATEWAY_PROMOTION_ACCEPTED,
        LifecycleEvent.ADAPTER_PROMOTION_RESUME_REQUESTED,
        LifecycleEvent.ADVANCE_TO_PROMOTION_DEADLINE,
    ):
        state = apply_event(state, event)

    assert "C019-POST-PROMOTION-01" in violations(state)


def test_explorer_reports_minimal_post_promotion_deadline_trace() -> None:
    parked = LifecycleState(
        successor=SuccessorState.PARKED,
        predecessor_complete=True,
        control=ControlState.PARKED,
        pause_owner=PauseOwner.PARKED,
        pause_deadline_kind=PauseDeadlineKind.PARKED,
        browser_park_generation=2,
        gateway_park_generation=2,
        adapter_park_generation=2,
        park_started_ms=0,
        pause_deadline_ms=185_000,
        promotion_deadline_ms=180_000,
    )

    traces = explore(parked, max_depth=2)

    assert traces["C019-POST-PROMOTION-01"] == (
        LifecycleEvent.BROWSER_PROMOTION_REQUESTED,
        LifecycleEvent.ADVANCE_TO_PROMOTION_DEADLINE,
    )


def test_park_and_promotion_generation_must_match_across_layers() -> None:
    state = LifecycleState(
        successor=SuccessorState.PARKED,
        control=ControlState.PARKED,
        pause_owner=PauseOwner.PARKED,
        pause_deadline_kind=PauseDeadlineKind.PARKED,
        browser_park_generation=8,
        gateway_park_generation=8,
        adapter_park_generation=9,
    )

    assert "C019-GENERATION-01" in violations(state)


def test_reused_park_generation_is_rejected() -> None:
    state = LifecycleState(
        next_park_generation=4,
        used_park_generations=frozenset({4}),
    )
    state = apply_event(state, LifecycleEvent.SUCCESSOR_PREFETCH)
    state = apply_event(state, LifecycleEvent.BROWSER_PARK_REQUESTED)

    assert "C019-GENERATION-01" in violations(state)


def test_requested_unit_must_match_gateway_expected_and_accepted_sequence() -> None:
    mismatch = with_unit_sequence_observation(
        LifecycleState(),
        requested_unit_seq=2,
        gateway_expected_unit_seq=1,
        accepted_unit_seq=None,
    )
    matched = with_unit_sequence_observation(
        LifecycleState(),
        requested_unit_seq=2,
        gateway_expected_unit_seq=2,
        accepted_unit_seq=2,
    )

    assert violations(mismatch) == ("C019-UNIT-SEQUENCE-01",)
    assert violations(matched) == ()


def test_complete_cross_layer_promotion_chain_is_valid() -> None:
    state = LifecycleState(
        successor=SuccessorState.PROMOTED,
        successor_was_promoted=True,
        predecessor_complete=True,
        pause_owner=PauseOwner.NONE,
        pause_deadline_kind=PauseDeadlineKind.NONE,
        browser_park_generation=12,
        gateway_park_generation=12,
        adapter_park_generation=12,
        browser_promotion_generation=12,
        gateway_promotion_generation=12,
        adapter_resume_generation=12,
        browser_promotion_requested=True,
        gateway_promotion_accepted=True,
        adapter_resume_requested=True,
        adapter_resume_acknowledged=True,
        reader_resumed_after_promotion=True,
        promotion_deadline_ms=5_000,
        now_ms=2_000,
    )

    assert violations(state) == ()


def test_provider_done_promotion_settles_as_terminal_noop_without_reader_revival() -> (
    None
):
    state = LifecycleState()
    for event in (
        LifecycleEvent.SUCCESSOR_PREFETCH,
        LifecycleEvent.BROWSER_PARK_REQUESTED,
        LifecycleEvent.GATEWAY_PARK_ACCEPTED,
        LifecycleEvent.ADAPTER_PARK_ACKNOWLEDGED,
        LifecycleEvent.PREDECESSOR_COMPLETE,
        LifecycleEvent.PROVIDER_DONE,
        LifecycleEvent.BROWSER_PROMOTION_REQUESTED,
        LifecycleEvent.GATEWAY_PROMOTION_ACCEPTED,
    ):
        state = apply_event(state, event)

    assert LifecycleEvent.ADAPTER_PROMOTION_RESUME_REQUESTED not in applicable_events(
        state
    )
    state = apply_event(state, LifecycleEvent.TERMINAL_NOOP_SETTLED)

    assert state.reader is ReaderState.EXITED
    assert state.reader_resumed_after_promotion is False
    assert state.terminal_noop_settled is True
    assert violations(state) == ()


def test_provider_failure_releases_park_owner_and_deadlines() -> None:
    state = parked_promotion_state()
    state = apply_event(state, LifecycleEvent.ADAPTER_PROMOTION_RESUME_REQUESTED)
    state = apply_event(state, LifecycleEvent.PROVIDER_FAILURE)

    assert state.successor is SuccessorState.FAILED
    assert state.pause_owner is PauseOwner.NONE
    assert state.pause_deadline_kind is PauseDeadlineKind.NONE
    assert state.pause_deadline_ms is None
    assert state.promotion_deadline_ms is None
    assert LifecycleEvent.ADVANCE_TO_PROMOTION_DEADLINE not in applicable_events(state)
    assert violations(state) == ()


def test_post_done_adapter_failure_releases_park_owner_and_deadlines() -> None:
    state = parked_promotion_state()
    state = apply_event(state, LifecycleEvent.PROVIDER_DONE)
    state = apply_event(state, LifecycleEvent.ADAPTER_FAILURE)

    assert state.successor is SuccessorState.FAILED
    assert state.pause_owner is PauseOwner.NONE
    assert state.pause_deadline_kind is PauseDeadlineKind.NONE
    assert state.pause_deadline_ms is None
    assert state.promotion_deadline_ms is None
    assert LifecycleEvent.ADVANCE_TO_PROMOTION_DEADLINE not in applicable_events(state)
    assert violations(state) == ()


def test_cancel_releases_park_owner_and_deadlines() -> None:
    state = parked_promotion_state()
    state = apply_event(state, LifecycleEvent.CANCEL)

    assert state.successor is SuccessorState.CANCELLED
    assert state.pause_owner is PauseOwner.NONE
    assert state.pause_deadline_kind is PauseDeadlineKind.NONE
    assert state.pause_deadline_ms is None
    assert state.promotion_deadline_ms is None
    assert LifecycleEvent.ADVANCE_TO_PROMOTION_DEADLINE not in applicable_events(state)
    assert violations(state) == ()
