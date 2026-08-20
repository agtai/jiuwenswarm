# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ScopeRef,
    TurnCommit,
)
from jiuwenswarm.server.live_voice.critical_token_safety import (
    AuthorizationState,
    ClarificationState,
    CommittedSpeechCandidate,
    CriticalTokenDecisionStatus,
    CriticalTokenKind,
    CriticalTokenPolicy,
    CriticalTokenReason,
    CriticalTokenSafetyGate,
    CriticalTokenSafetyViolation,
    DispatchAuthorization,
    EvidenceSource,
    GuardDispatchStatus,
    ProtectedRoute,
    SpeechAlternativeEvidence,
)


def scope(*, project: str = "project-1") -> ScopeRef:
    return ScopeRef("subject-1", project, "session-1", Assurance.AUTHENTICATED)


def commit(
    text: str,
    number: int,
    *,
    interaction: str = "interaction-1",
    project: str = "project-1",
    clarification_id: str | None = None,
    supersedes: str | None = None,
    input_generation: int | None = None,
) -> TurnCommit:
    generation = number if input_generation is None else input_generation
    provenance: dict[str, object] = {
        "provider": "fallback-browser-speech",
        "generation": generation,
        "critical_token_input": {"input_generation": generation},
    }
    if clarification_id is not None and supersedes is not None:
        provenance["critical_token_clarification"] = {
            "clarification_id": clarification_id,
            "supersedes_commit_id": supersedes,
            "input_generation": generation,
        }
    return TurnCommit.from_dict(
        {
            "contract_version": "live-voice.contract.v2",
            "commit_id": f"commit-{number}",
            "turn_id": f"turn-{number}",
            "interaction_id": interaction,
            "text": text,
            "hypothesis_provenance": provenance,
            "scope": scope(project=project).to_dict(),
            "context_refs": [],
            "committed_at": f"2026-08-05T08:00:{number:02d}Z",
        }
    )


def candidate(
    text: str,
    number: int,
    *,
    confidence: float | None = 0.99,
    alternatives: tuple[tuple[str, float | None], ...] | None = None,
    interaction: str = "interaction-1",
    project: str = "project-1",
    is_final: bool = True,
    source: EvidenceSource = EvidenceSource.SPEECH,
    uncertainty_reasons: tuple[str, ...] = (),
    supersedes: str | None = None,
    clarification_id: str | None = None,
    raw_text: str | None = None,
    input_generation: int | None = None,
) -> CommittedSpeechCandidate:
    generation = number if input_generation is None else input_generation
    evidence = alternatives or ((text, confidence),)
    return CommittedSpeechCandidate(
        commit(
            text,
            number,
            interaction=interaction,
            project=project,
            clarification_id=clarification_id,
            supersedes=supersedes,
            input_generation=generation,
        ),
        tuple(
            SpeechAlternativeEvidence(
                raw_text if raw_text is not None and index == 0 else value,
                value,
                score,
            )
            for index, (value, score) in enumerate(evidence)
        ),
        input_generation=generation,
        is_final=is_final,
        source=source,
        uncertainty_reasons=uncertainty_reasons,
        supersedes_commit_id=supersedes,
    )


def protected_effects() -> dict[str, int]:
    return {
        "agent": 0,
        "tool": 0,
        "task": 0,
        "audio": 0,
        "history": 0,
        "store": 0,
    }


def mutate_all(effects: dict[str, int]):
    def mutate(turn: TurnCommit) -> str:
        for key in effects:
            effects[key] += 1
        return turn.text

    return mutate


def test_policy_detects_general_critical_categories_and_configured_terms() -> None:
    policy = CriticalTokenPolicy(domain_terms=("WidgetProtocol",))
    observations = policy.scan(
        "Do not run `git push` for WidgetProtocol build_task 42 on "
        "2026-08-05 from feature/safe at C:\\repo\\app.py SHA 1e76dbd6."
    )
    kinds = {item.kind for item in observations}
    assert {
        CriticalTokenKind.NEGATION,
        CriticalTokenKind.NUMBER,
        CriticalTokenKind.DATE_OR_TIME,
        CriticalTokenKind.SHA,
        CriticalTokenKind.PATH_OR_BRANCH,
        CriticalTokenKind.IDENTIFIER,
        CriticalTokenKind.COMMAND,
        CriticalTokenKind.SIDE_EFFECT_VERB,
        CriticalTokenKind.DOMAIN_TERM,
    } <= kinds

    identifier_samples = policy.scan(
        "call pkg.module() with ${PROJECT_ID} and 123e4567-e89b-12d3-a456-426614174000"
    )
    assert all(
        CriticalTokenKind.IDENTIFIER
        in {item.kind for item in identifier_samples if value in item.text}
        for value in ("pkg.module", "PROJECT_ID", "123e4567")
    )


def test_low_risk_natural_language_with_unknown_confidence_is_not_blocked() -> None:
    decision = CriticalTokenPolicy().evaluate(
        candidate("请解释这个概念", 1, confidence=None)
    )
    assert decision.status is CriticalTokenDecisionStatus.ELIGIBLE
    assert decision.reasons == ()
    assert decision.critical_tokens == ()


def test_explicit_critical_uncertainty_fails_closed_when_token_kind_is_unknown() -> (
    None
):
    result = CriticalTokenSafetyGate().evaluate(
        candidate(
            "please explain foobar",
            1,
            uncertainty_reasons=("provider marked an unknown product token",),
        )
    )
    assert result.decision.status is CriticalTokenDecisionStatus.CLARIFICATION_REQUIRED
    assert result.decision.reasons == (
        CriticalTokenReason.EXPLICIT_CRITICAL_UNCERTAINTY,
    )
    assert result.decision.critical_tokens == ()
    assert result.clarification is not None
    assert "critical uncertainty" in result.clarification.prompt
    assert result.authorization is None


def test_alternative_low_risk_wording_does_not_block_matching_critical_tokens() -> None:
    decision = CriticalTokenPolicy().evaluate(
        candidate(
            "请运行 build_task 42 并给我摘要",
            1,
            alternatives=(
                ("请运行 build_task 42 并给我摘要", 0.99),
                ("请运行 build_task 42 然后给我总结", 0.95),
            ),
        )
    )
    assert decision.status is CriticalTokenDecisionStatus.ELIGIBLE
    assert decision.reasons == ()


def test_raw_display_critical_token_change_requires_clarification() -> None:
    decision = CriticalTokenPolicy().evaluate(
        candidate(
            "run build_task 42",
            1,
            raw_text="run build_task 24",
        )
    )
    assert decision.status is CriticalTokenDecisionStatus.CLARIFICATION_REQUIRED
    assert CriticalTokenReason.CRITICAL_ALTERNATIVES_DISAGREE in decision.reasons


def test_letter_only_hex_sha_is_critical_and_unknown_speech_requires_clarification() -> (
    None
):
    decision = CriticalTokenPolicy().evaluate(
        candidate("checkout deadbeef", 1, confidence=None)
    )
    assert decision.status is CriticalTokenDecisionStatus.CLARIFICATION_REQUIRED
    assert CriticalTokenReason.CRITICAL_CONFIDENCE_UNKNOWN in decision.reasons
    assert any(
        token.kind is CriticalTokenKind.SHA and token.text == "deadbeef"
        for token in decision.critical_tokens
    )


@pytest.mark.parametrize(
    ("selected", "alternative"),
    [
        ("deploy Build_Task 42", "deploy build_task 42"),
        ("delete 41 not 42", "delete 42 not 41"),
        ("运行42次", "运行24次"),
        ("checkout main", "checkout feature-safe"),
        ("git push main", "git push master"),
        (
            'remove "C:\\Program Files\\Alpha"',
            'remove "C:\\Program Files\\Beta"',
        ),
        ("create the task on August 5", "create the task on September 5"),
        ("create five tasks at 8 AM", "create nine tasks at 8 PM"),
    ],
)
def test_critical_case_or_order_disagreement_requires_clarification(
    selected: str, alternative: str
) -> None:
    decision = CriticalTokenPolicy().evaluate(
        candidate(
            selected,
            1,
            alternatives=((selected, 0.99), (alternative, 0.98)),
        )
    )
    assert decision.status is CriticalTokenDecisionStatus.CLARIFICATION_REQUIRED
    assert CriticalTokenReason.CRITICAL_ALTERNATIVES_DISAGREE in decision.reasons


def test_quoted_path_with_spaces_is_one_complete_critical_observation() -> None:
    observations = CriticalTokenPolicy().scan('remove "C:\\Program Files\\Alpha"')
    assert any(
        token.kind is CriticalTokenKind.PATH_OR_BRANCH
        and token.text == '"C:\\Program Files\\Alpha"'
        for token in observations
    )


@pytest.mark.parametrize(
    "text",
    ("checkout main", "checkout feature-safe", "切换到main分支"),
)
def test_contextual_simple_branch_name_is_critical(text: str) -> None:
    decision = CriticalTokenPolicy().evaluate(candidate(text, 1, confidence=None))
    assert decision.status is CriticalTokenDecisionStatus.CLARIFICATION_REQUIRED
    assert CriticalTokenReason.CRITICAL_CONFIDENCE_UNKNOWN in decision.reasons
    assert CriticalTokenKind.PATH_OR_BRANCH in {
        token.kind for token in decision.critical_tokens
    }


def test_clear_critical_input_passes_without_replacing_action_confirmation() -> None:
    decision = CriticalTokenPolicy().evaluate(
        candidate(
            "git push feature/safe 42",
            1,
            alternatives=(
                ("git push feature/safe 42", 0.99),
                ("git push feature/safe 42", 0.95),
            ),
        )
    )
    assert decision.status is CriticalTokenDecisionStatus.ELIGIBLE
    assert decision.requires_downstream_confirmation is True
    assert (
        CriticalTokenPolicy()
        .evaluate(candidate("rm app.py", 2))
        .requires_downstream_confirmation
        is True
    )


@pytest.mark.parametrize(
    ("text", "alternatives", "expected_reason"),
    [
        (
            "deploy build_task 42 to feature/safe",
            None,
            CriticalTokenReason.CRITICAL_CONFIDENCE_UNKNOWN,
        ),
        (
            "deploy build_task 42 to feature/safe",
            None,
            CriticalTokenReason.CRITICAL_LOW_CONFIDENCE,
        ),
        (
            "deploy build_task 42 to feature/safe",
            (
                ("deploy build_task 42 to feature/safe", 0.99),
                ("do not deploy build_task 24 to feature/safe", 0.98),
            ),
            CriticalTokenReason.CRITICAL_ALTERNATIVES_DISAGREE,
        ),
    ],
)
def test_uncertain_critical_input_requires_explainable_clarification_and_zero_effects(
    text: str,
    alternatives: tuple[tuple[str, float | None], ...] | None,
    expected_reason: CriticalTokenReason,
) -> None:
    confidence = (
        None
        if expected_reason is CriticalTokenReason.CRITICAL_CONFIDENCE_UNKNOWN
        else 0.2
    )
    if alternatives is not None:
        confidence = 0.99
    gate = CriticalTokenSafetyGate()
    effects = protected_effects()
    result = gate.evaluate(
        candidate(text, 1, confidence=confidence, alternatives=alternatives)
    )
    assert result.decision.status is CriticalTokenDecisionStatus.CLARIFICATION_REQUIRED
    assert expected_reason in result.decision.reasons
    assert result.clarification is not None
    assert result.authorization is None
    assert "critical tokens" in result.clarification.prompt
    assert effects == protected_effects()


def test_commit_text_must_match_selected_hypothesis_before_any_effect() -> None:
    original = candidate("run build_task 42", 1)
    mismatched = replace(
        original,
        alternatives=(
            SpeechAlternativeEvidence(
                "run build_task 24",
                "run build_task 24",
                0.99,
            ),
        ),
    )
    result = CriticalTokenSafetyGate().evaluate(mismatched)
    assert result.decision.status is CriticalTokenDecisionStatus.BLOCKED
    assert result.decision.reasons == (CriticalTokenReason.COMMIT_HYPOTHESIS_MISMATCH,)
    assert result.authorization is None

    retried_with_changed_evidence = CriticalTokenSafetyGate()
    first = retried_with_changed_evidence.evaluate(mismatched)
    assert first.decision.status is CriticalTokenDecisionStatus.BLOCKED
    retry = retried_with_changed_evidence.evaluate(original)
    assert retry.decision.reasons == (CriticalTokenReason.STALE_INPUT,)
    assert retry.authorization is None


def test_corrected_confirmation_dispatches_whole_protected_route_exactly_once() -> None:
    gate = CriticalTokenSafetyGate()
    effects = protected_effects()
    initial = gate.evaluate(candidate("run build_task 41", 1, confidence=0.2))
    assert initial.clarification is not None
    assert effects == protected_effects()

    corrected = candidate(
        "run build_task 42",
        2,
        confidence=None,
        source=EvidenceSource.EXPLICIT_TEXT,
        supersedes="commit-1",
        clarification_id=initial.clarification.clarification_id,
    )
    resolved = gate.resolve(
        initial.clarification.clarification_id,
        corrected,
        confirmed=True,
    )
    assert resolved.decision.status is CriticalTokenDecisionStatus.ELIGIBLE
    assert resolved.authorization is not None
    assert (
        resolved.authorization.clarification_id
        == initial.clarification.clarification_id
    )
    assert (
        gate.clarification_state(initial.clarification.clarification_id)
        is ClarificationState.RESOLVED
    )
    assert effects == protected_effects()

    first = gate.dispatch(
        resolved.authorization, ProtectedRoute.AGENT, mutate_all(effects)
    )
    replay = gate.dispatch(
        resolved.authorization, ProtectedRoute.AGENT, mutate_all(effects)
    )
    stale_resolution = gate.resolve(
        initial.clarification.clarification_id,
        corrected,
        confirmed=True,
    )
    assert first.status is GuardDispatchStatus.DISPATCHED
    assert first.value == "run build_task 42"
    assert replay.status is GuardDispatchStatus.DUPLICATE
    assert stale_resolution.decision.reasons == (
        CriticalTokenReason.STALE_CLARIFICATION,
    )
    assert effects == {key: 1 for key in effects}


def test_confirmation_must_be_explicit_and_correction_must_be_new_bound_turn() -> None:
    gate = CriticalTokenSafetyGate()
    initial = gate.evaluate(candidate("delete app.py", 1, confidence=None))
    assert initial.clarification is not None
    correction = candidate(
        "delete app.py",
        2,
        source=EvidenceSource.EXPLICIT_TEXT,
        supersedes="commit-1",
        clarification_id=initial.clarification.clarification_id,
    )

    unconfirmed = gate.resolve(
        initial.clarification.clarification_id,
        correction,
        confirmed=False,
    )
    same_turn = replace(
        correction,
        commit=TurnCommit.from_dict(
            {
                **correction.commit.to_dict(),
                "turn_id": "turn-1",
            }
        ),
    )
    invalid_turn = gate.resolve(
        initial.clarification.clarification_id,
        same_turn,
        confirmed=True,
    )
    assert unconfirmed.decision.reasons == (
        CriticalTokenReason.EXPLICIT_CLARIFICATION_CONFIRMATION_REQUIRED,
    )
    assert invalid_turn.decision.reasons == (
        CriticalTokenReason.CORRECTION_REQUIRES_NEW_TURN,
    )
    assert (
        gate.clarification_state(initial.clarification.clarification_id)
        is ClarificationState.PENDING
    )


def test_cancelled_clarification_rejects_late_confirmation_with_zero_effects() -> None:
    gate = CriticalTokenSafetyGate()
    effects = protected_effects()
    initial = gate.evaluate(candidate("delete app.py", 1, confidence=None))
    assert initial.clarification is not None
    clarification_id = initial.clarification.clarification_id
    assert gate.cancel_clarification(clarification_id) is ClarificationState.CANCELLED

    late = gate.resolve(
        clarification_id,
        candidate(
            "delete app.py",
            2,
            source=EvidenceSource.EXPLICIT_TEXT,
            supersedes="commit-1",
            clarification_id=clarification_id,
        ),
        confirmed=True,
    )
    assert late.decision.reasons == (CriticalTokenReason.STALE_CLARIFICATION,)
    assert late.authorization is None
    assert effects == protected_effects()


def test_replacement_fences_old_clarification_and_old_authorization() -> None:
    gate = CriticalTokenSafetyGate()
    old_pending = gate.evaluate(candidate("run build_task 41", 1, confidence=None))
    assert old_pending.clarification is not None
    replacement = gate.evaluate(candidate("请解释这个概念", 2))
    assert replacement.authorization is not None
    assert (
        gate.clarification_state(old_pending.clarification.clarification_id)
        is ClarificationState.REPLACED
    )

    stale = gate.resolve(
        old_pending.clarification.clarification_id,
        candidate(
            "run build_task 42",
            3,
            source=EvidenceSource.EXPLICIT_TEXT,
            supersedes="commit-1",
            clarification_id=old_pending.clarification.clarification_id,
        ),
        confirmed=True,
    )
    assert stale.decision.reasons == (CriticalTokenReason.STALE_CLARIFICATION,)

    newer = gate.evaluate(candidate("另一个普通问题", 4))
    assert newer.authorization is not None
    rejected = gate.dispatch(
        replacement.authorization, ProtectedRoute.AGENT, lambda turn: turn.text
    )
    assert rejected.status is GuardDispatchStatus.REJECTED
    assert rejected.reason == "AUTHORIZATION_REPLACED"


def test_releasing_replaced_commit_preserves_successor_authorization_index() -> None:
    gate = CriticalTokenSafetyGate()
    old = gate.evaluate(candidate("ordinary question", 1))
    successor = gate.evaluate(candidate("another ordinary question", 2))
    unrelated = gate.evaluate(
        candidate(
            "unrelated ordinary question",
            3,
            interaction="interaction-2",
            input_generation=1,
        )
    )
    assert old.authorization is not None
    assert successor.authorization is not None
    assert unrelated.authorization is not None

    gate.release_commit(old.authorization.commit_id)

    successor_effects = protected_effects()
    old_effects = protected_effects()
    unrelated_effects = protected_effects()
    old_dispatch = gate.dispatch(
        old.authorization, ProtectedRoute.AGENT, mutate_all(old_effects)
    )
    successor_dispatch = gate.dispatch(
        successor.authorization,
        ProtectedRoute.AGENT,
        mutate_all(successor_effects),
    )
    successor_replay = gate.dispatch(
        successor.authorization,
        ProtectedRoute.AGENT,
        mutate_all(successor_effects),
    )
    unrelated_dispatch = gate.dispatch(
        unrelated.authorization,
        ProtectedRoute.AGENT,
        mutate_all(unrelated_effects),
    )

    assert old_dispatch.status is GuardDispatchStatus.REJECTED
    assert old_dispatch.reason == "AUTHORIZATION_NOT_ISSUED"
    assert old_effects == protected_effects()
    assert successor_dispatch.status is GuardDispatchStatus.DISPATCHED
    assert successor_replay.status is GuardDispatchStatus.DUPLICATE
    assert successor_effects == {key: 1 for key in successor_effects}
    assert unrelated_dispatch.status is GuardDispatchStatus.DISPATCHED
    assert unrelated_effects == {key: 1 for key in unrelated_effects}


def test_releasing_replaced_commit_preserves_successor_clarification_index() -> None:
    gate = CriticalTokenSafetyGate()
    old = gate.evaluate(candidate("run build_task 41", 1, confidence=None))
    successor = gate.evaluate(candidate("run build_task 42", 2, confidence=None))
    assert old.clarification is not None
    assert successor.clarification is not None
    assert (
        gate.clarification_state(old.clarification.clarification_id)
        is ClarificationState.REPLACED
    )

    gate.release_commit(old.clarification.source_commit_id)
    closed = gate.close_interaction("interaction-1")

    assert closed.clarification_id == successor.clarification.clarification_id
    assert closed.clarification_state is ClarificationState.CANCELLED
    assert (
        gate.clarification_state(successor.clarification.clarification_id)
        is ClarificationState.CANCELLED
    )
    late = gate.resolve(
        successor.clarification.clarification_id,
        candidate(
            "run build_task 42",
            3,
            source=EvidenceSource.EXPLICIT_TEXT,
            supersedes=successor.clarification.source_commit_id,
            clarification_id=successor.clarification.clarification_id,
            input_generation=3,
        ),
        confirmed=True,
    )
    assert late.decision.reasons == (CriticalTokenReason.INTERACTION_CLOSED,)
    assert late.authorization is None


def test_concurrent_release_and_replacement_linearize_on_successor_authority() -> None:
    for iteration in range(8):
        gate = CriticalTokenSafetyGate()
        old = gate.evaluate(candidate("ordinary question", 1))
        assert old.authorization is not None
        barrier = Barrier(2)

        def release_old() -> None:
            barrier.wait()
            gate.release_commit(old.authorization.commit_id)

        def issue_successor():
            barrier.wait()
            return gate.evaluate(candidate("successor question", 2))

        with ThreadPoolExecutor(max_workers=2) as executor:
            release_future = executor.submit(release_old)
            successor_future = executor.submit(issue_successor)
            release_future.result()
            successor = successor_future.result()

        assert successor.authorization is not None
        effects = protected_effects()
        dispatched = gate.dispatch(
            successor.authorization,
            ProtectedRoute.AGENT,
            mutate_all(effects),
        )
        replay = gate.dispatch(
            successor.authorization,
            ProtectedRoute.AGENT,
            mutate_all(effects),
        )
        assert dispatched.status is GuardDispatchStatus.DISPATCHED, iteration
        assert replay.status is GuardDispatchStatus.DUPLICATE, iteration
        assert effects == {key: 1 for key in effects}


def test_delayed_older_generation_cannot_replace_newer_authorization() -> None:
    gate = CriticalTokenSafetyGate()
    newer = gate.evaluate(candidate("当前问题", 2, input_generation=2))
    assert newer.authorization is not None
    delayed = gate.evaluate(candidate("迟到问题", 1, input_generation=1))
    effects = protected_effects()
    dispatched = gate.dispatch(
        newer.authorization, ProtectedRoute.AGENT, mutate_all(effects)
    )
    assert delayed.decision.reasons == (CriticalTokenReason.STALE_INPUT_GENERATION,)
    assert delayed.authorization is None
    assert dispatched.status is GuardDispatchStatus.DISPATCHED
    assert effects == {key: 1 for key in effects}


def test_newer_blocked_generation_fences_old_authorization() -> None:
    gate = CriticalTokenSafetyGate()
    older = gate.evaluate(candidate("先前问题", 1, input_generation=1))
    assert older.authorization is not None
    blocked_candidate = candidate(
        "run build_task 42",
        2,
        input_generation=2,
    )
    blocked_candidate = replace(
        blocked_candidate,
        alternatives=(
            SpeechAlternativeEvidence(
                "run build_task 24",
                "run build_task 24",
                0.99,
            ),
        ),
    )
    blocked = gate.evaluate(blocked_candidate)
    effects = protected_effects()
    stale_dispatch = gate.dispatch(
        older.authorization, ProtectedRoute.AGENT, mutate_all(effects)
    )
    assert blocked.decision.status is CriticalTokenDecisionStatus.BLOCKED
    assert stale_dispatch.status is GuardDispatchStatus.REJECTED
    assert stale_dispatch.reason == "AUTHORIZATION_REPLACED"
    assert effects == protected_effects()


def test_different_commit_at_same_generation_conflicts_without_fencing_current() -> (
    None
):
    gate = CriticalTokenSafetyGate()
    current = gate.evaluate(candidate("当前问题", 1, input_generation=1))
    assert current.authorization is not None
    conflict = gate.evaluate(candidate("冲突问题", 2, input_generation=1))
    effects = protected_effects()
    dispatched = gate.dispatch(
        current.authorization, ProtectedRoute.AGENT, mutate_all(effects)
    )
    assert conflict.decision.reasons == (CriticalTokenReason.INPUT_GENERATION_CONFLICT,)
    assert dispatched.status is GuardDispatchStatus.DISPATCHED
    assert effects == {key: 1 for key in effects}


def test_unprovenanced_generation_cannot_fence_current_authorization() -> None:
    gate = CriticalTokenSafetyGate()
    current = gate.evaluate(candidate("当前问题", 1, input_generation=1))
    assert current.authorization is not None
    forged_generation = replace(
        candidate("伪造新问题", 2, input_generation=2),
        input_generation=3,
    )
    blocked = gate.evaluate(forged_generation)
    effects = protected_effects()
    dispatched = gate.dispatch(
        current.authorization, ProtectedRoute.AGENT, mutate_all(effects)
    )
    assert blocked.decision.reasons == (
        CriticalTokenReason.INPUT_GENERATION_PROVENANCE_MISMATCH,
    )
    assert dispatched.status is GuardDispatchStatus.DISPATCHED
    assert effects == {key: 1 for key in effects}


@pytest.mark.parametrize(
    ("provenance_generation", "input_generation"),
    ((True, 1), (False, 0)),
)
def test_boolean_input_generation_provenance_never_authorizes_or_mutates(
    provenance_generation: bool,
    input_generation: int,
) -> None:
    gate = CriticalTokenSafetyGate()
    input_candidate = candidate(
        "普通问题",
        1,
        input_generation=input_generation,
    )
    commit_payload = input_candidate.commit.to_dict()
    commit_payload["hypothesis_provenance"]["critical_token_input"] = {
        "input_generation": provenance_generation
    }
    forged = replace(
        input_candidate,
        commit=TurnCommit.from_dict(commit_payload),
    )
    effects = protected_effects()

    rejected = gate.evaluate(forged)

    assert rejected.decision.reasons == (
        CriticalTokenReason.INPUT_GENERATION_PROVENANCE_MISMATCH,
    )
    assert rejected.authorization is None
    assert effects == protected_effects()


def test_unprovenanced_correction_cannot_fence_pending_clarification() -> None:
    gate = CriticalTokenSafetyGate()
    pending = gate.evaluate(candidate("run build_task 42", 1, confidence=None))
    assert pending.clarification is not None
    correction = candidate(
        "run build_task 43",
        2,
        clarification_id=pending.clarification.clarification_id,
        supersedes="commit-1",
    )
    commit_payload = correction.commit.to_dict()
    commit_payload["hypothesis_provenance"]["critical_token_input"] = {
        "input_generation": 1
    }
    forged = replace(correction, commit=TurnCommit.from_dict(commit_payload))

    rejected = gate.resolve(
        pending.clarification.clarification_id,
        forged,
        confirmed=True,
    )
    assert rejected.decision.reasons == (
        CriticalTokenReason.INPUT_GENERATION_PROVENANCE_MISMATCH,
    )
    assert (
        gate.clarification_state(pending.clarification.clarification_id)
        is ClarificationState.PENDING
    )

    resolved = gate.resolve(
        pending.clarification.clarification_id,
        correction,
        confirmed=True,
    )
    assert resolved.authorization is not None


@pytest.mark.parametrize("provenance_generation", (True, False))
def test_boolean_clarification_generation_never_resolves_or_mutates(
    provenance_generation: bool,
) -> None:
    gate = CriticalTokenSafetyGate()
    pending = gate.evaluate(
        candidate(
            "run build_task 42",
            1,
            confidence=None,
            input_generation=0,
        )
    )
    assert pending.clarification is not None
    correction = candidate(
        "run build_task 43",
        2,
        input_generation=1,
        clarification_id=pending.clarification.clarification_id,
        supersedes="commit-1",
    )
    commit_payload = correction.commit.to_dict()
    commit_payload["hypothesis_provenance"]["critical_token_clarification"][
        "input_generation"
    ] = provenance_generation
    forged = replace(correction, commit=TurnCommit.from_dict(commit_payload))
    effects = protected_effects()

    rejected = gate.resolve(
        pending.clarification.clarification_id,
        forged,
        confirmed=True,
    )

    assert rejected.decision.reasons == (
        CriticalTokenReason.CLARIFICATION_BINDING_MISMATCH,
    )
    assert rejected.authorization is None
    assert (
        gate.clarification_state(pending.clarification.clarification_id)
        is ClarificationState.PENDING
    )
    assert effects == protected_effects()


def test_wrong_interaction_scope_or_superseded_commit_cannot_resolve() -> None:
    gate = CriticalTokenSafetyGate()
    initial = gate.evaluate(candidate("push feature/safe", 1, confidence=None))
    assert initial.clarification is not None
    clarification_id = initial.clarification.clarification_id

    wrong_interaction = candidate(
        "push feature/safe",
        2,
        interaction="interaction-2",
        source=EvidenceSource.EXPLICIT_TEXT,
        supersedes="commit-1",
        clarification_id=clarification_id,
    )
    wrong_scope = candidate(
        "push feature/safe",
        3,
        project="project-2",
        source=EvidenceSource.EXPLICIT_TEXT,
        supersedes="commit-1",
        clarification_id=clarification_id,
    )
    wrong_source = candidate(
        "push feature/safe",
        4,
        source=EvidenceSource.EXPLICIT_TEXT,
        supersedes="commit-other",
        clarification_id=clarification_id,
    )
    missing_provenance = candidate(
        "push feature/safe",
        5,
        source=EvidenceSource.EXPLICIT_TEXT,
        supersedes="commit-1",
    )
    for invalid in (
        wrong_interaction,
        wrong_scope,
        wrong_source,
        missing_provenance,
    ):
        result = gate.resolve(clarification_id, invalid, confirmed=True)
        assert result.decision.reasons == (
            CriticalTokenReason.CLARIFICATION_BINDING_MISMATCH,
        )
        assert result.authorization is None
    assert gate.clarification_state(clarification_id) is ClarificationState.PENDING


def test_still_uncertain_spoken_correction_replaces_but_does_not_dispatch() -> None:
    gate = CriticalTokenSafetyGate()
    first = gate.evaluate(candidate("run build_task 41", 1, confidence=None))
    assert first.clarification is not None
    second = gate.resolve(
        first.clarification.clarification_id,
        candidate(
            "run build_task 42",
            2,
            confidence=None,
            supersedes="commit-1",
            clarification_id=first.clarification.clarification_id,
        ),
        confirmed=True,
    )
    assert second.clarification is not None
    assert second.authorization is None
    assert (
        gate.clarification_state(first.clarification.clarification_id)
        is ClarificationState.REPLACED
    )
    assert (
        gate.clarification_state(second.clarification.clarification_id)
        is ClarificationState.PENDING
    )


def test_non_final_candidate_and_explicit_uncertainty_fail_closed() -> None:
    policy = CriticalTokenPolicy()
    non_final = policy.evaluate(candidate("run build_task 42", 1, is_final=False))
    uncertain = policy.evaluate(
        candidate(
            "run build_task 42",
            2,
            uncertainty_reasons=("domain resolver conflict",),
        )
    )
    assert non_final.status is CriticalTokenDecisionStatus.BLOCKED
    assert non_final.reasons == (CriticalTokenReason.FINAL_REQUIRED,)
    assert uncertain.status is CriticalTokenDecisionStatus.CLARIFICATION_REQUIRED
    assert CriticalTokenReason.EXPLICIT_CRITICAL_UNCERTAINTY in uncertain.reasons


def test_evidence_and_token_limits_fail_closed_without_issuing_authorization() -> None:
    evidence_limited = CriticalTokenSafetyGate(
        CriticalTokenPolicy(max_text_chars=8)
    ).evaluate(candidate("run build_task 42", 1))
    token_limited = CriticalTokenSafetyGate(
        CriticalTokenPolicy(max_critical_tokens=1)
    ).evaluate(candidate("run build_task 42", 2))
    assert evidence_limited.decision.reasons == (
        CriticalTokenReason.EVIDENCE_LIMIT_EXCEEDED,
    )
    assert token_limited.decision.reasons == (
        CriticalTokenReason.CRITICAL_TOKEN_LIMIT_EXCEEDED,
    )
    assert evidence_limited.authorization is None
    assert token_limited.authorization is None


def test_concurrent_dispatch_consumes_one_authorization_once() -> None:
    gate = CriticalTokenSafetyGate()
    result = gate.evaluate(candidate("普通问题", 1))
    assert result.authorization is not None
    effects = protected_effects()

    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = tuple(
            executor.map(
                lambda _: gate.dispatch(
                    result.authorization,
                    ProtectedRoute.AGENT,
                    mutate_all(effects),
                ),
                range(16),
            )
        )
    assert sum(item.status is GuardDispatchStatus.DISPATCHED for item in outcomes) == 1
    assert sum(item.status is GuardDispatchStatus.DUPLICATE for item in outcomes) == 15
    assert effects == {key: 1 for key in effects}


def test_route_failure_consumes_authorization_and_cannot_retry_unknown_effect() -> None:
    gate = CriticalTokenSafetyGate()
    result = gate.evaluate(candidate("普通问题", 1))
    assert result.authorization is not None
    calls = 0

    def fail_after_possible_effect(_: TurnCommit) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("downstream failed after an unknown effect boundary")

    with pytest.raises(RuntimeError):
        gate.dispatch(
            result.authorization, ProtectedRoute.AGENT, fail_after_possible_effect
        )
    replay = gate.dispatch(
        result.authorization, ProtectedRoute.AGENT, fail_after_possible_effect
    )
    assert calls == 1
    assert replay.status is GuardDispatchStatus.DUPLICATE
    assert (
        gate.authorization_state(result.authorization.authorization_id)
        is AuthorizationState.CONSUMED
    )


def test_cancelled_authorization_and_forged_authorization_never_dispatch() -> None:
    gate = CriticalTokenSafetyGate()
    result = gate.evaluate(candidate("普通问题", 1))
    assert result.authorization is not None
    effects = protected_effects()
    assert (
        gate.cancel_authorization(result.authorization.authorization_id)
        is AuthorizationState.CANCELLED
    )
    cancelled = gate.dispatch(
        result.authorization, ProtectedRoute.AGENT, mutate_all(effects)
    )
    forged = replace(result.authorization, commit_id="commit-forged")
    rejected = gate.dispatch(forged, ProtectedRoute.AGENT, mutate_all(effects))
    assert cancelled.status is GuardDispatchStatus.REJECTED
    assert rejected.status is GuardDispatchStatus.REJECTED
    assert effects == protected_effects()


def test_interaction_close_fences_pending_clarification_and_ready_route() -> None:
    gate = CriticalTokenSafetyGate()
    pending = gate.evaluate(candidate("run build_task 42", 1, confidence=None))
    assert pending.clarification is not None
    closed_pending = gate.close_interaction("interaction-1")
    assert closed_pending.clarification_state is ClarificationState.CANCELLED

    delayed_correction = candidate(
        "run build_task 43",
        2,
        supersedes="commit-1",
        clarification_id=pending.clarification.clarification_id,
    )
    rejected_correction = gate.resolve(
        pending.clarification.clarification_id,
        delayed_correction,
        confirmed=True,
    )
    rejected_reopen = gate.evaluate(candidate("ordinary question", 3))
    assert rejected_correction.decision.reasons == (
        CriticalTokenReason.INTERACTION_CLOSED,
    )
    assert rejected_reopen.decision.reasons == (CriticalTokenReason.INTERACTION_CLOSED,)
    assert rejected_correction.authorization is None
    assert rejected_reopen.authorization is None

    ready = gate.evaluate(
        candidate("普通问题", 4, interaction="interaction-2", input_generation=1)
    )
    assert ready.authorization is not None
    closed_ready = gate.close_interaction("interaction-2")
    effects = protected_effects()
    rejected = gate.dispatch(
        ready.authorization, ProtectedRoute.AGENT, mutate_all(effects)
    )
    assert closed_ready.authorization_state is AuthorizationState.CANCELLED
    assert rejected.status is GuardDispatchStatus.REJECTED
    assert rejected.reason == "INTERACTION_CLOSED"
    assert effects == protected_effects()

    delayed_newer = gate.evaluate(
        candidate("普通问题", 5, interaction="interaction-2", input_generation=2)
    )
    assert delayed_newer.decision.reasons == (CriticalTokenReason.INTERACTION_CLOSED,)
    assert delayed_newer.authorization is None

    unaffected = gate.evaluate(
        candidate("普通问题", 6, interaction="interaction-3", input_generation=1)
    )
    assert unaffected.authorization is not None


def test_bounded_gate_releases_terminal_commit_and_interaction_state() -> None:
    gate = CriticalTokenSafetyGate(capacity=2)
    first = gate.evaluate(candidate("ordinary question", 1))
    second = gate.evaluate(
        candidate(
            "another question", 2, interaction="interaction-2", input_generation=1
        )
    )
    assert first.authorization is not None
    assert second.authorization is not None

    full = gate.evaluate(
        candidate("third question", 3, interaction="interaction-3", input_generation=1)
    )
    assert full.decision.reasons == (CriticalTokenReason.GATE_CAPACITY_EXCEEDED,)

    gate.release_commit(first.authorization.commit_id)
    assert first.authorization.authorization_id not in gate._authorizations
    gate.release_interaction("interaction-1")
    admitted = gate.evaluate(
        candidate("third question", 3, interaction="interaction-3", input_generation=1)
    )
    assert admitted.authorization is not None
    assert len(gate._commit_interactions) <= 2
    assert len(gate._latest_input_generation) <= 2

    gate.reset()
    assert gate._commit_interactions == {}
    assert gate._latest_input_generation == {}


def test_bounded_gate_rejects_correction_before_growing_commit_state() -> None:
    gate = CriticalTokenSafetyGate(capacity=1)
    pending = gate.evaluate(candidate("run build_task 42", 1, confidence=None))
    assert pending.clarification is not None
    corrected = candidate(
        "run build_task 42",
        2,
        supersedes="commit-1",
        clarification_id=pending.clarification.clarification_id,
        input_generation=2,
    )

    rejected = gate.resolve(
        pending.clarification.clarification_id,
        corrected,
        confirmed=True,
    )

    assert rejected.decision.reasons == (CriticalTokenReason.GATE_CAPACITY_EXCEEDED,)
    assert len(gate._commit_interactions) == 1


def test_feature_off_is_explicit_bypass_and_fallback_does_not_relax_flag_on() -> None:
    uncertain = candidate("git push feature/safe 42", 1, confidence=None)
    enabled = CriticalTokenSafetyGate().evaluate(uncertain)
    disabled_gate = CriticalTokenSafetyGate(enabled=False)
    disabled = disabled_gate.evaluate(uncertain)
    assert enabled.decision.status is CriticalTokenDecisionStatus.CLARIFICATION_REQUIRED
    assert enabled.authorization is None
    assert disabled.decision.status is CriticalTokenDecisionStatus.BYPASSED
    assert disabled.authorization is not None
    assert disabled.authorization.safety_bypassed is True


def test_feature_off_preserves_committed_final_integrity_checks() -> None:
    partial = candidate("git push feature/safe 42", 1, is_final=False)
    unprovenanced = replace(
        candidate("git push feature/safe 42", 2), input_generation=3
    )
    mismatched = replace(
        candidate("git push feature/safe 42", 3),
        commit=commit("git push feature/other 42", 3),
    )

    for rejected, reason in (
        (partial, CriticalTokenReason.FINAL_REQUIRED),
        (unprovenanced, CriticalTokenReason.INPUT_GENERATION_PROVENANCE_MISMATCH),
        (mismatched, CriticalTokenReason.COMMIT_HYPOTHESIS_MISMATCH),
    ):
        result = CriticalTokenSafetyGate(enabled=False).evaluate(rejected)
        assert result.decision.status is CriticalTokenDecisionStatus.BLOCKED
        assert result.decision.reasons == (reason,)
        assert result.authorization is None


def test_feature_off_does_not_apply_clarification_policy_limits() -> None:
    policy = CriticalTokenPolicy(
        max_text_chars=4,
        max_alternatives=1,
        max_critical_tokens=1,
    )
    input_candidate = candidate(
        "git push feature/safe 42",
        1,
        confidence=None,
        alternatives=(
            ("git push feature/safe 42", None),
            ("git push feature/other 24", None),
        ),
    )
    result = CriticalTokenSafetyGate(policy, enabled=False).evaluate(input_candidate)
    assert result.decision.status is CriticalTokenDecisionStatus.BYPASSED
    assert result.authorization is not None
    assert result.authorization.safety_bypassed is True


def test_interactions_keep_independent_clarification_state() -> None:
    gate = CriticalTokenSafetyGate()
    first = gate.evaluate(
        candidate("run build_task 41", 1, confidence=None, interaction="interaction-1")
    )
    second = gate.evaluate(
        candidate("run build_task 42", 2, confidence=None, interaction="interaction-2")
    )
    assert first.clarification is not None
    assert second.clarification is not None
    assert (
        gate.clarification_state(first.clarification.clarification_id)
        is ClarificationState.PENDING
    )
    assert (
        gate.clarification_state(second.clarification.clarification_id)
        is ClarificationState.PENDING
    )


def test_invalid_inputs_and_commit_id_conflict_fail_closed() -> None:
    with pytest.raises(CriticalTokenSafetyViolation) as raised:
        CriticalTokenPolicy(minimum_confidence=1.1)
    assert raised.value.reason == "INVALID_CONFIDENCE_THRESHOLD"
    with pytest.raises(CriticalTokenSafetyViolation) as raised:
        CriticalTokenPolicy(max_alternatives=0)
    assert raised.value.reason == "INVALID_POLICY_LIMIT"
    with pytest.raises(CriticalTokenSafetyViolation) as raised:
        SpeechAlternativeEvidence("x", "x", True)
    assert raised.value.reason == "INVALID_CONFIDENCE"

    gate = CriticalTokenSafetyGate()
    accepted = gate.evaluate(candidate("普通问题", 1))
    assert accepted.authorization is not None
    changed = candidate("另一个普通问题", 1)
    conflict = gate.evaluate(changed)
    assert conflict.decision.reasons == (CriticalTokenReason.COMMIT_ID_CONFLICT,)
    assert conflict.authorization is None


@pytest.mark.parametrize("route", tuple(ProtectedRoute))
def test_invalid_or_unissued_route_authorization_has_zero_effects(
    route: ProtectedRoute,
) -> None:
    gate = CriticalTokenSafetyGate()
    effects = protected_effects()
    forged = DispatchAuthorization(
        "authorization-forged",
        "interaction-1",
        "turn-1",
        "commit-1",
        1,
        None,
        False,
    )
    rejected = gate.dispatch(forged, route, mutate_all(effects))
    assert rejected.status is GuardDispatchStatus.REJECTED
    assert rejected.reason == "AUTHORIZATION_NOT_ISSUED"
    assert effects == protected_effects()
