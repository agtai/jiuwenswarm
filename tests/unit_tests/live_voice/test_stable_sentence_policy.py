from __future__ import annotations

import json
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseRef
from jiuwenswarm.server.live_voice.agent_bridge import AgentEvent
from jiuwenswarm.server.live_voice.stable_sentence_policy import (
    FinalReconciliationDisposition,
    StableSentenceStreamState,
    StableSentenceViolation,
    candidate_content,
    commit_candidate,
    observe_agent_event,
    reconcile_final,
)


FIXTURES = (
    Path(__file__).parents[2]
    / "fixtures"
    / "live_voice"
    / "stable_sentence_policy_v1.json"
)
RESPONSE = ResponseRef("interaction-1", "response-1", 0)


def event(
    seq: int,
    event_type: str,
    text: str | None = None,
    *,
    interaction_id: str = "interaction-1",
    request_id: str = "request-1",
) -> AgentEvent:
    return AgentEvent(
        request_id=request_id,
        interaction_id=interaction_id,
        turn_id="turn-1",
        commit_id="commit-1",
        seq=seq,
        event_type=event_type,
        source_provenance="formal",
        text=text,
        capability="agent.chat",
    )


def test_waits_for_lookahead_then_emits_exact_utf8_span() -> None:
    state = StableSentenceStreamState.create(RESPONSE)

    first = observe_agent_event(
        state, event(0, "chat.delta", "Paris is the capital. ")
    )
    second = observe_agent_event(
        first.state, event(1, "chat.delta", "It is in France")
    )

    assert first.candidate is None
    assert second.candidate is not None
    assert candidate_content(second.state, second.candidate) == (
        b"Paris is the capital. "
    )
    assert second.candidate.source_start_utf8 == 0
    assert second.candidate.source_end_utf8 == len(b"Paris is the capital. ")


def test_boundary_trailer_split_across_deltas_remains_pending() -> None:
    state = StableSentenceStreamState.create(RESPONSE)

    for seq, fragment in enumerate(("Hello.", "\u201d", " Next")):
        observed = observe_agent_event(
            state, event(seq, "chat.delta", fragment)
        )
        state = observed.state

    assert observed.candidate is not None
    assert candidate_content(state, observed.candidate) == "Hello.\u201d ".encode()


def test_public_fixtures_reconcile_without_prompt_specific_policy() -> None:
    cases = json.loads(FIXTURES.read_text(encoding="utf-8"))

    for case in cases:
        state = StableSentenceStreamState.create(RESPONSE)
        candidate = None
        for seq, fragment in enumerate(case["fragments"]):
            observed = observe_agent_event(state, event(seq, "chat.delta", fragment))
            state = observed.state
            if observed.candidate is not None:
                candidate = observed.candidate
        expected = case["expected_candidate"]
        assert (
            None if candidate is None else candidate_content(state, candidate).decode()
        ) == expected, case["case_id"]
        if candidate is not None:
            state = commit_candidate(state, candidate.candidate_id).state
        reconciled = reconcile_final(state, case["final"])
        assert reconciled.disposition.value == case["expected_disposition"], case[
            "case_id"
        ]


def test_barrier_discards_only_mutable_candidate_and_never_committed_prefix() -> None:
    state = StableSentenceStreamState.create(RESPONSE)
    observed = observe_agent_event(
        state,
        event(0, "chat.delta", "I will check that. The next sentence starts"),
    )
    assert observed.candidate is not None

    barrier = observe_agent_event(observed.state, event(1, "chat.tool_call"))

    assert barrier.candidate is None
    assert barrier.discarded_candidate_ids == (observed.candidate.candidate_id,)
    assert barrier.state.committed_utf8_end == 0
    assert barrier.barrier == "chat.tool_call"


def test_commit_is_exact_and_final_returns_only_unspoken_tail() -> None:
    state = StableSentenceStreamState.create(RESPONSE)
    observed = observe_agent_event(
        state,
        event(0, "chat.delta", "First sentence. Second sentence begins"),
    )
    assert observed.candidate is not None
    committed = commit_candidate(observed.state, observed.candidate.candidate_id)

    reconciled = reconcile_final(
        committed.state, "First sentence. Second sentence completes."
    )

    assert reconciled.disposition is FinalReconciliationDisposition.EXACT_PREFIX
    assert reconciled.final_tail_utf8 == b"Second sentence completes."
    assert reconciled.correction_required is False


def test_final_prefix_mismatch_after_commit_requires_correction() -> None:
    observed = observe_agent_event(
        StableSentenceStreamState.create(RESPONSE),
        event(0, "chat.delta", "Paris is the capital. More follows"),
    )
    assert observed.candidate is not None
    committed = commit_candidate(observed.state, observed.candidate.candidate_id)

    reconciled = reconcile_final(committed.state, "Paris is the largest city.")

    assert (
        reconciled.disposition
        is FinalReconciliationDisposition.REWRITE_AFTER_COMMIT
    )
    assert reconciled.final_tail_utf8 == b"Paris is the largest city."
    assert reconciled.correction_required is True


@pytest.mark.parametrize(
    ("events", "reason"),
    [
        ((event(1, "chat.delta", "gap"),), "AGENT_EVENT_SEQUENCE_GAP"),
        (
            (
                event(0, "chat.delta", "first"),
                event(0, "chat.delta", "changed"),
            ),
            "AGENT_EVENT_REPLAY_CONFLICT",
        ),
        (
            (event(0, "chat.delta", "wrong", interaction_id="interaction-2"),),
            "AGENT_EVENT_RESPONSE_MISMATCH",
        ),
        ((event(0, "chat.delta", "bad\x00text"),), "INVALID_AGENT_TEXT"),
    ],
)
def test_invalid_identity_sequence_and_content_fail_before_state_change(
    events: tuple[AgentEvent, ...], reason: str
) -> None:
    state = StableSentenceStreamState.create(RESPONSE)
    with pytest.raises(StableSentenceViolation) as error:
        for item in events:
            state = observe_agent_event(state, item).state
    assert error.value.reason == reason


def test_exact_event_replay_and_exact_final_replay_are_idempotent() -> None:
    original = event(0, "chat.delta", "First sentence. More")
    observed = observe_agent_event(StableSentenceStreamState.create(RESPONSE), original)
    replayed = observe_agent_event(observed.state, original)
    assert replayed.state == observed.state
    assert replayed.candidate == observed.candidate

    assert observed.candidate is not None
    committed = commit_candidate(observed.state, observed.candidate.candidate_id)
    first = reconcile_final(committed.state, "First sentence. More complete.")
    second = reconcile_final(first.state, "First sentence. More complete.")
    assert second.disposition is FinalReconciliationDisposition.EXACT_REPLAY
    assert second.correction_required is False
    assert first.state.event_fingerprints == ()
    assert first.state.text_event_spans == ()


def test_wrong_candidate_id_fails_without_advancing_committed_span() -> None:
    observed = observe_agent_event(
        StableSentenceStreamState.create(RESPONSE),
        event(0, "chat.delta", "First sentence. More"),
    )
    with pytest.raises(StableSentenceViolation) as error:
        commit_candidate(observed.state, "candidate-wrong")
    assert error.value.reason == "STABLE_SENTENCE_CANDIDATE_MISMATCH"
    assert observed.state.committed_utf8_end == 0


def test_successor_candidate_retains_its_own_agent_event_span() -> None:
    first = observe_agent_event(
        StableSentenceStreamState.create(RESPONSE),
        event(0, "chat.delta", "First sentence. "),
    )
    second = observe_agent_event(
        first.state,
        event(1, "chat.delta", "Second sentence starts"),
    )
    assert second.candidate is not None
    committed = commit_candidate(second.state, second.candidate.candidate_id)

    successor = observe_agent_event(
        committed.state,
        event(2, "chat.delta", ". Third sentence starts"),
    )

    assert successor.candidate is not None
    assert candidate_content(successor.state, successor.candidate) == (
        b"Second sentence starts. "
    )
    assert successor.candidate.first_agent_event_seq == 1
    assert successor.candidate.last_agent_event_seq == 2


def test_long_append_only_stream_reaches_authoritative_final() -> None:
    """A valid long response must not exhaust the old 256-event pilot bound."""

    text = "First sentence. Long continuation "
    first = observe_agent_event(
        StableSentenceStreamState.create(RESPONSE),
        event(0, "chat.delta", "First sentence. "),
    )
    second = observe_agent_event(
        first.state, event(1, "chat.delta", "Long continuation ")
    )
    assert second.candidate is not None
    state = commit_candidate(second.state, second.candidate.candidate_id).state

    for seq in range(2, 495):
        state = observe_agent_event(state, event(seq, "chat.delta", "x")).state
        text += "x"

    final = observe_agent_event(state, event(495, "chat.final", text))
    reconciled = reconcile_final(final.state, text)

    assert final.state.next_agent_event_seq == 496
    assert reconciled.disposition is FinalReconciliationDisposition.EXACT_PREFIX
    assert reconciled.correction_required is False


def test_content_limit_allows_its_authoritative_final_event() -> None:
    text = "x" * 32_768
    state = StableSentenceStreamState(
        response_ref=RESPONSE,
        observed_text=text,
        observed_utf8_end=32_768,
        boundary_scan_character=32_768,
        next_agent_event_seq=33_024,
        non_text_event_count=256,
        request_id="request-1",
        turn_id="turn-1",
        commit_id="commit-1",
        source_provenance="formal",
    )

    final = observe_agent_event(state, event(33_024, "chat.final", text))
    reconciled = reconcile_final(final.state, text)

    assert final.state.next_agent_event_seq == 33_025
    assert reconciled.disposition is FinalReconciliationDisposition.EXACT_PREFIX


def test_event_after_content_derived_stream_bound_fails_closed() -> None:
    state = StableSentenceStreamState(
        response_ref=RESPONSE,
        next_agent_event_seq=33_025,
    )

    with pytest.raises(StableSentenceViolation) as error:
        observe_agent_event(state, event(33_025, "chat.delta", "x"))

    assert error.value.reason == "AGENT_EVENT_LIMIT_EXCEEDED"


def test_non_text_event_reserve_is_enforced_independently() -> None:
    state = StableSentenceStreamState.create(RESPONSE)
    for seq in range(256):
        state = observe_agent_event(state, event(seq, "chat.tool_call")).state

    with pytest.raises(StableSentenceViolation) as error:
        observe_agent_event(state, event(256, "chat.tool_result"))

    assert error.value.reason == "AGENT_NON_TEXT_EVENT_LIMIT_EXCEEDED"
