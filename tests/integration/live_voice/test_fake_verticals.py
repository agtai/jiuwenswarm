# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    InputCommitState,
    ResponseRef,
    ScopeRef,
    TerminalOutcome,
    TurnCommit,
)
from jiuwenswarm.server.live_voice.fake_verticals import (
    FakeIntegratedVerticals,
    FakeTrackAvailability,
    FakeVerticalViolation,
)
from jiuwenswarm.server.live_voice.voice_task_bridge import (
    TaskIntent,
    VoiceTaskBridgeViolation,
)


SCOPE = ScopeRef("subject", "project", "session", Assurance.AUTHENTICATED)


def turn_commit(text: str = "Check inventory") -> TurnCommit:
    return TurnCommit.from_dict(
        {
            "contract_version": "live-voice.contract.v2",
            "commit_id": "commit-1",
            "turn_id": "turn-1",
            "interaction_id": "interaction-1",
            "text": text,
            "hypothesis_provenance": {"provider": "deterministic-speech-fake"},
            "scope": SCOPE.to_dict(),
            "context_refs": [],
            "committed_at": "2026-08-04T08:00:00Z",
        }
    )


def task_intent(state: InputCommitState = InputCommitState.COMMITTED) -> TaskIntent:
    return TaskIntent(
        state=state,
        operation="task.create",
        request_id="request-1",
        command_id="command-1",
        scope=SCOPE,
        origin_commit_id="commit-1",
        name="inventory",
        instruction="check inventory",
    )


def test_p1_uses_only_final_committed_text_and_truthful_fake_route() -> None:
    result = FakeIntegratedVerticals().run_p1(
        turn_commit(), ResponseRef("interaction-1", "response-1", 0)
    )
    assert [event.kind.value for event in result.recognition_events] == [
        "partial",
        "final",
    ]
    assert result.partial_synthesis_events == ()
    assert result.committed_text == "Check inventory"
    assert [event.kind.value for event in result.synthesis_events] == [
        "started",
        "chunk",
        "completed",
    ]
    assert result.route.implementation_class == "demo_substitute"
    assert result.route.safe_reason == "DETERMINISTIC_FAKE_ONLY"


def test_p1_rejects_recognition_that_differs_from_committed_text() -> None:
    with pytest.raises(FakeVerticalViolation) as raised:
        FakeIntegratedVerticals().run_p1(
            turn_commit(),
            ResponseRef("interaction-1", "response-1", 0),
            recognized_display_text="Different text",
        )
    assert raised.value.reason == "COMMITTED_TEXT_MISMATCH"


def test_p1_rejects_cross_interaction_response_before_speech_effects() -> None:
    with pytest.raises(FakeVerticalViolation) as raised:
        FakeIntegratedVerticals().run_p1(
            turn_commit(), ResponseRef("other-interaction", "response-1", 0)
        )
    assert raised.value.reason == "RESPONSE_SCOPE_MISMATCH"


def test_p2_is_non_blocking_and_replacement_fences_delayed_output() -> None:
    result = FakeIntegratedVerticals().run_p2(turn_commit(), replace_response=True)
    assert result.submit_returned_before_completion is True
    assert result.replacement_response is not None
    assert result.agent_events[0].commit_id == "commit-1"
    assert result.agent_events[0].turn_id == "turn-1"
    assert result.output_effects == ()
    assert result.stale_output_blocked is True
    original = next(
        item
        for item in result.snapshot.responses
        if item.ref == result.original_response
    )
    assert original.fenced is True


def test_p2_current_response_can_select_only_presentational_effects() -> None:
    result = FakeIntegratedVerticals().run_p2(turn_commit(), replace_response=False)
    assert [effect.effect_type for effect in result.output_effects] == [
        "ui.render",
        "history.append",
        "audio.enqueue",
    ]
    assert result.stale_output_blocked is False
    assert all("task" not in effect.effect_type for effect in result.output_effects)


def test_invalid_control_flags_reject_before_vertical_state() -> None:
    with pytest.raises(FakeVerticalViolation) as raised:
        FakeIntegratedVerticals(FakeTrackAvailability(p1="yes"))
    assert raised.value.reason == "INVALID_AVAILABILITY"

    with pytest.raises(FakeVerticalViolation) as raised:
        FakeIntegratedVerticals().run_p2(turn_commit(), replace_response="yes")
    assert raised.value.reason == "INVALID_REPLACEMENT_FLAG"


def test_p3_preserves_exact_identity_and_returns_progress_without_tts() -> None:
    result = FakeIntegratedVerticals().run_p3(
        task_intent(), SCOPE, outcome=TerminalOutcome.COMPLETED
    )
    assert result.task_id == result.terminal_task.task_id
    assert result.attempt_id == result.terminal_task.attempt_id
    assert [progress.state for progress in result.progress] == [
        "accepted",
        "running",
        "terminal",
    ]
    assert result.progress[-1].outcome == "completed"
    assert all(progress.task_id == result.task_id for progress in result.progress)
    assert all(progress.attempt_id == result.attempt_id for progress in result.progress)
    assert result.tts_effects == ()
    assert result.route.implementation_class == "demo_substitute"


def test_faults_are_isolated_and_unavailable_tracks_never_look_formal() -> None:
    verticals = FakeIntegratedVerticals(
        FakeTrackAvailability(p1=False, p2=True, p3alpha=True)
    )
    routes = {route.segment_id: route for route in verticals.routes()}
    assert routes["p1.speech"].implementation_class == "unsupported"
    assert routes["p1.speech"].safe_reason == "TRACK_UNAVAILABLE"
    assert all(route.implementation_class != "formal" for route in routes.values())
    with pytest.raises(FakeVerticalViolation) as raised:
        verticals.run_p1(turn_commit(), ResponseRef("interaction-1", "response-1", 0))
    assert raised.value.reason == "TRACK_UNAVAILABLE"

    with pytest.raises(VoiceTaskBridgeViolation) as raised:
        verticals.run_p3(task_intent(InputCommitState.PARTIAL), SCOPE)
    assert raised.value.reason == "INPUT_NOT_COMMITTED"

    successful = verticals.run_p3(task_intent(), SCOPE)
    assert successful.terminal_task.outcome is TerminalOutcome.COMPLETED


@pytest.mark.parametrize(
    ("availability", "segment_id", "runner"),
    [
        (
            FakeTrackAvailability(p1=False),
            "p1.speech",
            lambda verticals: verticals.run_p1(
                turn_commit(), ResponseRef("interaction-1", "response-1", 0)
            ),
        ),
        (
            FakeTrackAvailability(p2=False),
            "p2.conversation",
            lambda verticals: verticals.run_p2(turn_commit(), replace_response=False),
        ),
        (
            FakeTrackAvailability(p3alpha=False),
            "p3alpha.task",
            lambda verticals: verticals.run_p3(task_intent(), SCOPE),
        ),
    ],
)
def test_each_unavailable_track_rejects_and_reports_unsupported(
    availability, segment_id, runner
) -> None:
    verticals = FakeIntegratedVerticals(availability)
    route = next(item for item in verticals.routes() if item.segment_id == segment_id)
    assert route.implementation_class == "unsupported"
    assert route.safe_reason == "TRACK_UNAVAILABLE"
    with pytest.raises(FakeVerticalViolation) as raised:
        runner(verticals)
    assert raised.value.reason == "TRACK_UNAVAILABLE"
