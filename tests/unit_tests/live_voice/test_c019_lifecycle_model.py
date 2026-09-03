# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from dataclasses import replace

import pytest

from tests.unit_tests.live_voice.c019_lifecycle_model import (
    ControlState,
    FailureCleanupSource,
    InterruptingCaptureState,
    LifecycleEvent,
    LifecycleState,
    NextPreparationState,
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
    fenced_callbacks_pending,
    from_adapter_snapshot,
    violations,
    with_identity_observation,
    with_spoken_barge_observation,
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


def spoken_barge_state() -> LifecycleState:
    state = apply_event(LifecycleState(), LifecycleEvent.TRANSPORT_ATTACH)
    state = apply_event(state, LifecycleEvent.SUCCESSOR_PREFETCH)
    state = apply_event(state, LifecycleEvent.SUCCESSOR_CAPTURE_READY)
    return apply_event(state, LifecycleEvent.SPOKEN_BARGE_IN)


def test_spoken_barge_fences_the_response_and_keeps_the_interrupting_capture() -> None:
    state = spoken_barge_state()

    assert state.outcome is OutcomeState.CANCELLED
    assert state.successor is SuccessorState.CANCELLED
    assert state.expected_transport_close is True
    assert state.interrupting_capture is InterruptingCaptureState.LIVE
    assert LifecycleEvent.AUDIO_DELTA not in applicable_events(state)
    assert LifecycleEvent.SUCCESSOR_PLAY not in applicable_events(state)
    assert violations(state) == ()


def test_spoken_barge_continuation_submits_exactly_one_new_turn() -> None:
    state = apply_event(spoken_barge_state(), LifecycleEvent.TRANSPORT_CLOSE)
    state = apply_event(state, LifecycleEvent.CAPTURE_END_OF_TURN)
    assert violations(state) == ()

    submitted = apply_event(state, LifecycleEvent.UNIFIED_SUBMIT)
    assert submitted.committed_submits_after_fence == 1
    assert submitted.interrupting_capture is InterruptingCaptureState.RELEASED
    assert violations(submitted) == ()
    assert LifecycleEvent.UNIFIED_SUBMIT not in applicable_events(submitted)

    duplicated = replace(submitted, committed_submits_after_fence=2)
    assert violations(duplicated) == ("C019-SPOKEN-BARGE-CONTINUATION-01",)


def test_spoken_barge_revoking_the_interrupting_capture_is_a_violation() -> None:
    state = apply_event(spoken_barge_state(), LifecycleEvent.CAPTURE_AUTHORITY_REVOKED)

    assert state.interrupting_capture is InterruptingCaptureState.REVOKED
    assert LifecycleEvent.CAPTURE_END_OF_TURN not in applicable_events(state)
    assert violations(state) == ("C019-SPOKEN-BARGE-CONTINUATION-01",)


def test_spoken_barge_rejects_late_effects_of_the_fenced_response() -> None:
    state = apply_event(spoken_barge_state(), LifecycleEvent.FENCED_RESPONSE_EFFECT)

    assert violations(state) == ("C019-SPOKEN-BARGE-CONTINUATION-01",)


@pytest.mark.parametrize(
    "event", (LifecycleEvent.STOP_REQUESTED, LifecycleEvent.EXIT_REQUESTED)
)
def test_stop_and_exit_release_the_capture_and_never_submit(
    event: LifecycleEvent,
) -> None:
    state = apply_event(LifecycleState(), LifecycleEvent.SUCCESSOR_CAPTURE_READY)
    state = apply_event(state, event)

    assert state.outcome is OutcomeState.CANCELLED
    assert state.interrupting_capture is InterruptingCaptureState.RELEASED
    assert LifecycleEvent.SPOKEN_BARGE_IN not in applicable_events(state)
    assert LifecycleEvent.UNIFIED_SUBMIT not in applicable_events(state)
    assert violations(state) == ()

    submitted = replace(state, committed_submits_after_fence=1)
    assert violations(submitted) == ("C019-SPOKEN-BARGE-CONTINUATION-01",)


def test_explorer_reaches_the_spoken_barge_continuation_violation() -> None:
    assert explore(LifecycleState(), max_depth=1) == {}
    assert "C019-SPOKEN-BARGE-CONTINUATION-01" in explore(LifecycleState(), max_depth=3)

    traces = explore(spoken_barge_state(), max_depth=1)
    assert traces["C019-SPOKEN-BARGE-CONTINUATION-01"] in {
        (LifecycleEvent.CAPTURE_AUTHORITY_REVOKED,),
        (LifecycleEvent.FENCED_RESPONSE_EFFECT,),
    }


def test_physical_a1_spoken_barge_observation_is_valid() -> None:
    # c019-task1-aba-20260903T175213Z/A1 long-0: barge fence 0.6 ms, then a
    # second EOT on the same capture and one new committed unified submit.
    state = with_spoken_barge_observation(
        LifecycleState(),
        fence="spoken_barge",
        interrupting_capture="released",
        committed_submits_after_fence=1,
        fenced_response_effects=0,
    )

    assert violations(state) == ()


def test_physical_b_spoken_barge_observation_is_a_violation() -> None:
    # c019-task1-aba-20260903T175213Z/B long-0: barge fence 0.8 ms, then the
    # Browser revoked the successor capture subject, the Gateway aborted its
    # streaming recognition (STREAMING_SPEECH_ROUTE_ABORTED), no second EOT
    # and no unified submit.
    state = with_spoken_barge_observation(
        LifecycleState(),
        fence="spoken_barge",
        interrupting_capture="revoked",
        committed_submits_after_fence=0,
        fenced_response_effects=0,
    )

    assert violations(state) == ("C019-SPOKEN-BARGE-CONTINUATION-01",)


def test_spoken_barge_observation_rejects_unknown_fence() -> None:
    with pytest.raises(ValueError, match="fence must be"):
        with_spoken_barge_observation(
            LifecycleState(),
            fence="barge",
            interrupting_capture="live",
            committed_submits_after_fence=0,
            fenced_response_effects=0,
        )


def test_spoken_barge_eot_without_submit_is_a_violation_once_settlement_elapses() -> (
    None
):
    state = apply_event(spoken_barge_state(), LifecycleEvent.CAPTURE_END_OF_TURN)
    # The transient window between EOT and the committed submit is normal.
    assert violations(state) == ()

    unsettled = apply_event(state, LifecycleEvent.CONTINUATION_SETTLEMENT_DEADLINE)
    assert violations(unsettled) == ("C019-SPOKEN-BARGE-CONTINUATION-01",)

    submitted = apply_event(state, LifecycleEvent.UNIFIED_SUBMIT)
    settled = apply_event(submitted, LifecycleEvent.CONTINUATION_SETTLEMENT_DEADLINE)
    assert violations(settled) == ()
    assert LifecycleEvent.CONTINUATION_SETTLEMENT_DEADLINE not in applicable_events(
        settled
    )


def test_settlement_deadline_with_the_capture_still_live_is_not_a_violation() -> None:
    state = apply_event(
        spoken_barge_state(), LifecycleEvent.CONTINUATION_SETTLEMENT_DEADLINE
    )

    assert state.interrupting_capture is InterruptingCaptureState.LIVE
    assert violations(state) == ()


@pytest.mark.parametrize(
    "event", (LifecycleEvent.STOP_REQUESTED, LifecycleEvent.EXIT_REQUESTED)
)
def test_stop_and_exit_settlement_never_demands_a_submit(
    event: LifecycleEvent,
) -> None:
    state = apply_event(LifecycleState(), LifecycleEvent.SUCCESSOR_CAPTURE_READY)
    state = apply_event(state, event)
    state = apply_event(state, LifecycleEvent.CONTINUATION_SETTLEMENT_DEADLINE)

    assert violations(state) == ()


def test_physical_b_observation_with_eot_but_no_submit_is_a_violation_when_settled() -> (
    None
):
    state = with_spoken_barge_observation(
        LifecycleState(),
        fence="spoken_barge",
        interrupting_capture="end_of_turn",
        committed_submits_after_fence=0,
        fenced_response_effects=0,
        settled=True,
    )

    assert violations(state) == ("C019-SPOKEN-BARGE-CONTINUATION-01",)


def one_ahead_state() -> LifecycleState:
    """Unit 1 playing, unit 2 buffered, unit 3 preparation in flight."""

    state = LifecycleState()
    for event in (
        LifecycleEvent.TRANSPORT_ATTACH,
        LifecycleEvent.SUCCESSOR_PREFETCH,
        LifecycleEvent.SUCCESSOR_CAPTURE_READY,
        LifecycleEvent.ACTIVE_UNIT_PLAYOUT,
        LifecycleEvent.SUCCESSOR_BUFFERED,
        LifecycleEvent.NEXT_PREPARATION_STARTED,
    ):
        state = apply_event(state, event)
    return state


def apply_all(
    state: LifecycleState, events: tuple[LifecycleEvent, ...]
) -> LifecycleState:
    for event in events:
        state = apply_event(state, event)
    return state


def test_spoken_barge_fences_the_active_unit_the_successor_and_the_preparation() -> (
    None
):
    state = apply_event(one_ahead_state(), LifecycleEvent.SPOKEN_BARGE_IN)

    assert state.active_unit_playing is False
    assert state.next_preparation is NextPreparationState.FENCED
    assert fenced_callbacks_pending(state) == 3
    assert LifecycleEvent.NEXT_PREPARATION_STARTED not in applicable_events(state)
    assert violations(state) == ()


def test_physical_b_sample_two_trace_violates_the_model() -> None:
    # c019-task1-aba-20260903T193642Z/B long-2: unit 1 promoted and playing,
    # unit 2 buffered, barge at 69060 ms (fence 2.3 ms), the barge handler
    # released the continuation authority, then a Product P1 failure cleanup
    # (release_resources_failed) revoked the interrupting capture; the Gateway
    # aborted its streaming recognition and no EOT or submit followed.
    state = apply_all(
        one_ahead_state(),
        (
            LifecycleEvent.SPOKEN_BARGE_IN,
            LifecycleEvent.BARGE_HANDLER_SETTLED,
            LifecycleEvent.FENCED_CALLBACK_FAILURE_CLEANUP,
            LifecycleEvent.CAPTURE_AUTHORITY_REVOKED,
        ),
    )

    assert state.failure_cleanup is FailureCleanupSource.FENCED
    assert violations(state) == (
        "C019-FENCED-CALLBACK-01",
        "C019-SPOKEN-BARGE-CONTINUATION-01",
    )


def test_physical_b_sample_two_observation_is_a_violation() -> None:
    state = with_spoken_barge_observation(
        LifecycleState(),
        fence="spoken_barge",
        interrupting_capture="revoked",
        committed_submits_after_fence=0,
        fenced_response_effects=0,
        failure_cleanup="fenced",
    )

    assert violations(state) == (
        "C019-FENCED-CALLBACK-01",
        "C019-SPOKEN-BARGE-CONTINUATION-01",
    )


@pytest.mark.parametrize(
    "settlement",
    (
        # cancel signal before the Provider rejection
        (
            LifecycleEvent.PREPARATION_CANCEL_SIGNAL,
            LifecycleEvent.PREPARATION_PROVIDER_REJECTED,
            LifecycleEvent.PREPARATION_SETTLED_CANCELLED,
            LifecycleEvent.STAGED_LOCAL_CLOSE,
            LifecycleEvent.BARGE_HANDLER_SETTLED,
        ),
        # Provider rejection before the cancel signal
        (
            LifecycleEvent.PREPARATION_PROVIDER_REJECTED,
            LifecycleEvent.PREPARATION_CANCEL_SIGNAL,
            LifecycleEvent.PREPARATION_SETTLED_CANCELLED,
            LifecycleEvent.STAGED_LOCAL_CLOSE,
            LifecycleEvent.BARGE_HANDLER_SETTLED,
        ),
        # deferred admission waiter: cancel signal alone settles the preparation
        (
            LifecycleEvent.PREPARATION_CANCEL_SIGNAL,
            LifecycleEvent.PREPARATION_SETTLED_CANCELLED,
            LifecycleEvent.STAGED_LOCAL_CLOSE,
            LifecycleEvent.BARGE_HANDLER_SETTLED,
        ),
        # staged local close before the barge handler
        (
            LifecycleEvent.STAGED_LOCAL_CLOSE,
            LifecycleEvent.BARGE_HANDLER_SETTLED,
            LifecycleEvent.PREPARATION_CANCEL_SIGNAL,
            LifecycleEvent.PREPARATION_PROVIDER_REJECTED,
            LifecycleEvent.PREPARATION_SETTLED_CANCELLED,
        ),
        # staged local close after the barge handler
        (
            LifecycleEvent.BARGE_HANDLER_SETTLED,
            LifecycleEvent.STAGED_LOCAL_CLOSE,
            LifecycleEvent.PREPARATION_PROVIDER_REJECTED,
            LifecycleEvent.PREPARATION_CANCEL_SIGNAL,
            LifecycleEvent.PREPARATION_SETTLED_CANCELLED,
        ),
    ),
    ids=(
        "cancel-then-reject",
        "reject-then-cancel",
        "cancel-only-waiter",
        "close-then-handler",
        "handler-then-close",
    ),
)
def test_spoken_barge_one_ahead_race_settles_as_owned_cancellations_then_submits_once(
    settlement: tuple[LifecycleEvent, ...],
) -> None:
    state = apply_all(one_ahead_state(), (LifecycleEvent.SPOKEN_BARGE_IN, *settlement))

    assert fenced_callbacks_pending(state) == 0
    assert state.next_preparation is NextPreparationState.SETTLED
    assert state.failure_cleanup is FailureCleanupSource.NONE
    assert state.interrupting_capture is InterruptingCaptureState.LIVE
    assert violations(state) == ()

    state = apply_all(
        state,
        (
            LifecycleEvent.TRANSPORT_CLOSE,
            LifecycleEvent.CAPTURE_END_OF_TURN,
            LifecycleEvent.UNIFIED_SUBMIT,
            LifecycleEvent.CONTINUATION_SETTLEMENT_DEADLINE,
        ),
    )
    assert state.committed_submits_after_fence == 1
    assert violations(state) == ()


@pytest.mark.parametrize(
    "race",
    (
        # the concurrent failure callback wins before the barge handler
        (
            LifecycleEvent.FENCED_CALLBACK_FAILURE_CLEANUP,
            LifecycleEvent.BARGE_HANDLER_SETTLED,
        ),
        # the barge handler settles first, then the fenced Provider rejection fails
        (
            LifecycleEvent.BARGE_HANDLER_SETTLED,
            LifecycleEvent.STAGED_LOCAL_CLOSE,
            LifecycleEvent.PREPARATION_PROVIDER_REJECTED,
            LifecycleEvent.FENCED_CALLBACK_FAILURE_CLEANUP,
        ),
        # the buffered successor's close callback fails instead of cancelling
        (
            LifecycleEvent.BARGE_HANDLER_SETTLED,
            LifecycleEvent.PREPARATION_CANCEL_SIGNAL,
            LifecycleEvent.PREPARATION_SETTLED_CANCELLED,
            LifecycleEvent.FENCED_CALLBACK_FAILURE_CLEANUP,
        ),
    ),
    ids=(
        "failure-before-handler",
        "provider-rejection-after-handler",
        "staged-close-failure",
    ),
)
def test_fenced_callback_entering_failure_cleanup_is_a_violation(
    race: tuple[LifecycleEvent, ...],
) -> None:
    state = apply_all(one_ahead_state(), (LifecycleEvent.SPOKEN_BARGE_IN, *race))

    assert violations(state) == ("C019-FENCED-CALLBACK-01",)
    revoked = apply_event(state, LifecycleEvent.CAPTURE_AUTHORITY_REVOKED)
    assert violations(revoked) == (
        "C019-FENCED-CALLBACK-01",
        "C019-SPOKEN-BARGE-CONTINUATION-01",
    )


def test_preparation_rejected_before_any_fence_is_an_external_failure() -> None:
    state = apply_event(one_ahead_state(), LifecycleEvent.PREPARATION_PROVIDER_REJECTED)

    assert state.failure_cleanup is FailureCleanupSource.EXTERNAL
    assert violations(state) == ()


def test_external_failure_after_spoken_barge_may_enter_cleanup_and_revoke() -> None:
    state = apply_all(
        one_ahead_state(),
        (
            LifecycleEvent.SPOKEN_BARGE_IN,
            LifecycleEvent.EXTERNAL_FAILURE_CLEANUP,
            LifecycleEvent.CAPTURE_AUTHORITY_REVOKED,
        ),
    )

    assert violations(state) == ()


@pytest.mark.parametrize(
    "event", (LifecycleEvent.STOP_REQUESTED, LifecycleEvent.EXIT_REQUESTED)
)
def test_stop_and_exit_settle_fenced_callbacks_as_owned_cancellations_without_submit(
    event: LifecycleEvent,
) -> None:
    state = apply_all(
        one_ahead_state(),
        (
            event,
            LifecycleEvent.STAGED_LOCAL_CLOSE,
            LifecycleEvent.BARGE_HANDLER_SETTLED,
            LifecycleEvent.PREPARATION_CANCEL_SIGNAL,
            LifecycleEvent.PREPARATION_SETTLED_CANCELLED,
            LifecycleEvent.CONTINUATION_SETTLEMENT_DEADLINE,
        ),
    )

    assert fenced_callbacks_pending(state) == 0
    assert LifecycleEvent.UNIFIED_SUBMIT not in applicable_events(state)
    assert violations(state) == ()
    failed = apply_all(
        one_ahead_state(), (event, LifecycleEvent.FENCED_CALLBACK_FAILURE_CLEANUP)
    )
    assert violations(failed) == ("C019-FENCED-CALLBACK-01",)


def test_explorer_reaches_the_fenced_callback_violation_from_the_one_ahead_race() -> (
    None
):
    assert explore(LifecycleState(), max_depth=1) == {}
    traces = explore(
        apply_event(one_ahead_state(), LifecycleEvent.SPOKEN_BARGE_IN), max_depth=1
    )
    assert traces["C019-FENCED-CALLBACK-01"] == (
        LifecycleEvent.FENCED_CALLBACK_FAILURE_CLEANUP,
    )


def test_fenced_unit_delivered_after_the_spoken_barge_must_be_discarded() -> None:
    fenced = apply_all(
        one_ahead_state(),
        (
            LifecycleEvent.SPOKEN_BARGE_IN,
            LifecycleEvent.BARGE_HANDLER_SETTLED,
            LifecycleEvent.STAGED_LOCAL_CLOSE,
            LifecycleEvent.PREPARATION_CANCEL_SIGNAL,
            LifecycleEvent.PREPARATION_SETTLED_CANCELLED,
            LifecycleEvent.FENCED_UNIT_DELIVERED,
        ),
    )
    assert violations(fenced) == ()

    discarded = apply_event(fenced, LifecycleEvent.FENCED_UNIT_DISCARDED)
    assert violations(discarded) == ()
    submitted = apply_all(
        discarded,
        (
            LifecycleEvent.TRANSPORT_CLOSE,
            LifecycleEvent.CAPTURE_END_OF_TURN,
            LifecycleEvent.UNIFIED_SUBMIT,
        ),
    )
    assert violations(submitted) == ()

    adopted = apply_event(fenced, LifecycleEvent.FENCED_UNIT_ADOPTED)
    assert violations(adopted) == ("C019-SPOKEN-BARGE-CONTINUATION-01",)


@pytest.mark.parametrize(
    "event", (LifecycleEvent.STOP_REQUESTED, LifecycleEvent.EXIT_REQUESTED)
)
def test_fenced_unit_after_stop_or_exit_must_be_discarded_without_submit(
    event: LifecycleEvent,
) -> None:
    state = apply_all(
        one_ahead_state(),
        (
            event,
            LifecycleEvent.FENCED_UNIT_DELIVERED,
            LifecycleEvent.FENCED_UNIT_DISCARDED,
        ),
    )
    assert violations(state) == ()
    assert LifecycleEvent.UNIFIED_SUBMIT not in applicable_events(state)
    adopted = apply_all(
        one_ahead_state(),
        (
            event,
            LifecycleEvent.FENCED_UNIT_DELIVERED,
            LifecycleEvent.FENCED_UNIT_ADOPTED,
        ),
    )
    assert violations(adopted) == ("C019-SPOKEN-BARGE-CONTINUATION-01",)
