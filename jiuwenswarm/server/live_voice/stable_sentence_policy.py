# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Pure response-local planning for conservative stable-sentence speech."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from enum import StrEnum

from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseRef
from jiuwenswarm.server.live_voice.agent_bridge import AgentEvent


POLICY_ID = "conservative-lookahead-v1"
_MAX_RESPONSE_UTF8 = 32_768
_MAX_CANDIDATE_UTF8 = 8_192
_MAX_AGENT_EVENTS = 256
_BARRIER_EVENTS = frozenset(
    {"chat.tool_call", "chat.tool_result", "chat.error", "chat.final"}
)
_TERMINAL_EVENTS = frozenset({"chat.error"})
_SENTENCE_END = frozenset("。！？!?；;.…")
_SENTENCE_TRAILER = frozenset("。！？!?；;.…”’」』】）》)]")
_ABBREVIATION = re.compile(
    r"(?:^|\s)(?:mr|mrs|ms|dr|prof|sr|jr|st|vs|etc)\.$", re.IGNORECASE
)


class StableSentenceViolation(ValueError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class FinalReconciliationDisposition(StrEnum):
    EXACT_PREFIX = "exact_prefix"
    REWRITE_BEFORE_COMMIT = "rewrite_before_commit"
    REWRITE_AFTER_COMMIT = "rewrite_after_commit"
    EXACT_REPLAY = "exact_replay"


@dataclass(frozen=True, slots=True)
class StableSentenceCandidate:
    response_ref: ResponseRef
    candidate_id: str
    candidate_seq: int
    source_start_utf8: int
    source_end_utf8: int
    content_ref: str
    first_agent_event_seq: int
    last_agent_event_seq: int
    stability_policy_id: str
    stability_evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StableSentenceStreamState:
    response_ref: ResponseRef
    observed_text: str = ""
    committed_utf8_end: int = 0
    next_agent_event_seq: int = 0
    next_candidate_seq: int = 0
    active_candidate: StableSentenceCandidate | None = None
    barrier_event_seq: int | None = None
    terminal: bool = False
    request_id: str | None = None
    turn_id: str | None = None
    commit_id: str | None = None
    source_provenance: str | None = None
    event_fingerprints: tuple[str, ...] = ()
    text_event_spans: tuple[tuple[int, int, int], ...] = ()
    promotion_blocked: bool = False
    final_text: str | None = None

    @classmethod
    def create(cls, response_ref: ResponseRef) -> StableSentenceStreamState:
        if not isinstance(response_ref, ResponseRef):
            raise StableSentenceViolation(
                "INVALID_RESPONSE_REF", "stable sentence state requires ResponseRef"
            )
        return cls(response_ref=response_ref)


@dataclass(frozen=True, slots=True)
class StableSentenceObservation:
    state: StableSentenceStreamState
    candidate: StableSentenceCandidate | None
    discarded_candidate_ids: tuple[str, ...]
    barrier: str | None


@dataclass(frozen=True, slots=True)
class StableSentenceCommit:
    state: StableSentenceStreamState
    candidate: StableSentenceCandidate


@dataclass(frozen=True, slots=True)
class StableSentenceReconciliation:
    state: StableSentenceStreamState
    disposition: FinalReconciliationDisposition
    final_tail_utf8: bytes
    correction_required: bool


def _has_forbidden_control(text: str) -> bool:
    return any(
        (ord(character) < 32 and character not in {"\t", "\n", "\r"})
        or ord(character) == 127
        for character in text
    )


def _require_text(text: object, *, allow_empty: bool = False) -> str:
    if not isinstance(text, str) or (not allow_empty and not text):
        raise StableSentenceViolation("INVALID_AGENT_TEXT", "Agent text is invalid")
    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError as error:
        raise StableSentenceViolation(
            "INVALID_AGENT_TEXT", "Agent text must contain Unicode scalars"
        ) from error
    if _has_forbidden_control(text) or len(encoded) > _MAX_RESPONSE_UTF8:
        raise StableSentenceViolation(
            "INVALID_AGENT_TEXT", "Agent text exceeds the closed content boundary"
        )
    return text


def _event_fingerprint(event: AgentEvent) -> str:
    encoded = json.dumps(
        {
            "request_id": event.request_id,
            "interaction_id": event.interaction_id,
            "turn_id": event.turn_id,
            "commit_id": event.commit_id,
            "seq": event.seq,
            "event_type": event.event_type,
            "source_provenance": event.source_provenance,
            "text": event.text,
            "capability": event.capability,
            "error_reason": event.error_reason,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_identity(
    state: StableSentenceStreamState, event: AgentEvent
) -> StableSentenceStreamState:
    if not isinstance(event, AgentEvent):
        raise StableSentenceViolation(
            "INVALID_AGENT_EVENT", "stable sentence policy requires AgentEvent"
        )
    if event.interaction_id != state.response_ref.interaction_id:
        raise StableSentenceViolation(
            "AGENT_EVENT_RESPONSE_MISMATCH",
            "Agent event interaction does not match the response",
        )
    fingerprint = _event_fingerprint(event)
    if event.seq < state.next_agent_event_seq:
        if (
            0 <= event.seq < len(state.event_fingerprints)
            and state.event_fingerprints[event.seq] == fingerprint
        ):
            return state
        raise StableSentenceViolation(
            "AGENT_EVENT_REPLAY_CONFLICT", "Agent event replay changed content"
        )
    if event.seq > state.next_agent_event_seq:
        raise StableSentenceViolation(
            "AGENT_EVENT_SEQUENCE_GAP", "Agent event sequence is not contiguous"
        )
    if event.seq >= _MAX_AGENT_EVENTS:
        raise StableSentenceViolation(
            "AGENT_EVENT_LIMIT_EXCEEDED", "Agent event bound was exceeded"
        )
    if state.request_id is not None and (
        event.request_id != state.request_id
        or event.turn_id != state.turn_id
        or event.commit_id != state.commit_id
        or event.source_provenance != state.source_provenance
    ):
        raise StableSentenceViolation(
            "AGENT_EVENT_RESPONSE_MISMATCH", "Agent event identity changed"
        )
    return replace(
        state,
        request_id=event.request_id,
        turn_id=event.turn_id,
        commit_id=event.commit_id,
        source_provenance=event.source_provenance,
        next_agent_event_seq=event.seq + 1,
        event_fingerprints=(*state.event_fingerprints, fingerprint),
    )


def _has_unclosed_code_fence(text: str) -> bool:
    return text.count("```") % 2 == 1


def _inside_code_fence(text: str, index: int) -> bool:
    return text[: index + 1].count("```") % 2 == 1


def _english_period_is_boundary(text: str, index: int) -> bool:
    previous = text[index - 1] if index else ""
    following = text[index + 1] if index + 1 < len(text) else ""
    if previous.isdigit() and following.isdigit():
        return False
    if following and (following.isalnum() or following == "_"):
        return False
    prefix = text[: index + 1]
    if _ABBREVIATION.search(prefix):
        return False
    return True


def _boundary_after(text: str, index: int) -> int | None:
    character = text[index]
    if character == ".":
        if not _english_period_is_boundary(text, index):
            return None
    elif character not in _SENTENCE_END:
        return None
    if _inside_code_fence(text, index):
        return None
    boundary = index + 1
    while boundary < len(text) and text[boundary] in _SENTENCE_TRAILER:
        boundary += 1
    while boundary < len(text) and text[boundary].isspace():
        boundary += 1
    if not text[boundary:].strip():
        return None
    return boundary


def _character_offset_for_utf8(text: str, byte_offset: int) -> int:
    encoded = text.encode("utf-8")
    try:
        return len(encoded[:byte_offset].decode("utf-8"))
    except UnicodeDecodeError as error:
        raise StableSentenceViolation(
            "INVALID_SOURCE_SPAN", "UTF-8 source offset split a scalar"
        ) from error


def _select_candidate(
    state: StableSentenceStreamState, last_event_seq: int
) -> StableSentenceCandidate | None:
    if (
        state.active_candidate is not None
        or state.promotion_blocked
        or _has_unclosed_code_fence(state.observed_text)
    ):
        return state.active_candidate
    start_character = _character_offset_for_utf8(
        state.observed_text, state.committed_utf8_end
    )
    boundary = next(
        (
            selected
            for index in range(start_character, len(state.observed_text))
            if (selected := _boundary_after(state.observed_text, index)) is not None
        ),
        None,
    )
    if boundary is None:
        return None
    source_end = len(state.observed_text[:boundary].encode("utf-8"))
    content = state.observed_text.encode("utf-8")[
        state.committed_utf8_end : source_end
    ]
    if not content or len(content) > _MAX_CANDIDATE_UTF8:
        raise StableSentenceViolation(
            "STABLE_SENTENCE_CANDIDATE_TOO_LARGE",
            "stable sentence candidate exceeds its closed bound",
        )
    content_ref = f"sha256:{hashlib.sha256(content).hexdigest()}"
    first_event_seq = next(
        (
            event_seq
            for event_seq, _start, end in state.text_event_spans
            if end > state.committed_utf8_end
        ),
        last_event_seq,
    )
    identity = hashlib.sha256(
        (
            f"{state.response_ref.response_id}\0"
            f"{state.response_ref.response_generation}\0"
            f"{state.next_candidate_seq}\0{state.committed_utf8_end}\0"
            f"{source_end}\0{content_ref}"
        ).encode("utf-8")
    ).hexdigest()[:32]
    return StableSentenceCandidate(
        response_ref=state.response_ref,
        candidate_id=f"stable-sentence:{identity}",
        candidate_seq=state.next_candidate_seq,
        source_start_utf8=state.committed_utf8_end,
        source_end_utf8=source_end,
        content_ref=content_ref,
        first_agent_event_seq=first_event_seq,
        last_agent_event_seq=last_event_seq,
        stability_policy_id=POLICY_ID,
        stability_evidence=("sentence_boundary", "visible_lookahead"),
    )


def observe_agent_event(
    state: StableSentenceStreamState, event: AgentEvent
) -> StableSentenceObservation:
    if not isinstance(state, StableSentenceStreamState):
        raise StableSentenceViolation(
            "INVALID_STABLE_SENTENCE_STATE", "stable sentence state is invalid"
        )
    if state.terminal:
        raise StableSentenceViolation(
            "STABLE_SENTENCE_TERMINAL", "terminal sentence state cannot advance"
        )
    prior_seq = state.next_agent_event_seq
    next_state = _validate_identity(state, event)
    if event.seq < prior_seq:
        replay_candidate = (
            next_state.active_candidate
            if next_state.active_candidate is not None
            and next_state.active_candidate.last_agent_event_seq == event.seq
            else None
        )
        return StableSentenceObservation(next_state, replay_candidate, (), None)

    if event.event_type == "chat.delta":
        fragment = _require_text(event.text)
        source_start = len(next_state.observed_text.encode("utf-8"))
        combined = f"{next_state.observed_text}{fragment}"
        _require_text(combined)
        source_end = len(combined.encode("utf-8"))
        next_state = replace(
            next_state,
            observed_text=combined,
            text_event_spans=(
                *next_state.text_event_spans,
                (event.seq, source_start, source_end),
            ),
        )
        candidate = _select_candidate(next_state, event.seq)
        if candidate is not None and next_state.active_candidate is None:
            next_state = replace(
                next_state,
                active_candidate=candidate,
                next_candidate_seq=next_state.next_candidate_seq + 1,
            )
        return StableSentenceObservation(next_state, candidate, (), None)

    if event.event_type in _BARRIER_EVENTS:
        discarded = (
            ()
            if next_state.active_candidate is None
            else (next_state.active_candidate.candidate_id,)
        )
        next_state = replace(
            next_state,
            active_candidate=None,
            barrier_event_seq=event.seq,
            promotion_blocked=True,
            terminal=event.event_type in _TERMINAL_EVENTS,
        )
        return StableSentenceObservation(
            next_state, None, discarded, event.event_type
        )

    return StableSentenceObservation(
        next_state, next_state.active_candidate, (), None
    )


def candidate_content(
    state: StableSentenceStreamState, candidate: StableSentenceCandidate
) -> bytes:
    if (
        not isinstance(state, StableSentenceStreamState)
        or not isinstance(candidate, StableSentenceCandidate)
        or candidate.response_ref != state.response_ref
    ):
        raise StableSentenceViolation(
            "STABLE_SENTENCE_CANDIDATE_MISMATCH",
            "candidate does not belong to the response",
        )
    encoded = state.observed_text.encode("utf-8")
    content = encoded[candidate.source_start_utf8 : candidate.source_end_utf8]
    if (
        not content
        or candidate.content_ref
        != f"sha256:{hashlib.sha256(content).hexdigest()}"
    ):
        raise StableSentenceViolation(
            "STABLE_SENTENCE_CONTENT_MISMATCH",
            "candidate content does not match its source span",
        )
    return content


def commit_candidate(
    state: StableSentenceStreamState, candidate_id: str
) -> StableSentenceCommit:
    candidate = state.active_candidate
    if (
        candidate is None
        or not isinstance(candidate_id, str)
        or candidate.candidate_id != candidate_id
    ):
        raise StableSentenceViolation(
            "STABLE_SENTENCE_CANDIDATE_MISMATCH",
            "only the exact active candidate can be committed",
        )
    candidate_content(state, candidate)
    return StableSentenceCommit(
        replace(
            state,
            committed_utf8_end=candidate.source_end_utf8,
            active_candidate=None,
        ),
        candidate,
    )


def reconcile_final(
    state: StableSentenceStreamState, final_text: str
) -> StableSentenceReconciliation:
    final_text = _require_text(final_text)
    if state.terminal:
        if state.final_text == final_text:
            return StableSentenceReconciliation(
                state,
                FinalReconciliationDisposition.EXACT_REPLAY,
                b"",
                False,
            )
        raise StableSentenceViolation(
            "FINAL_REWRITE_AFTER_FINAL", "final text cannot change after terminal"
        )

    final_utf8 = final_text.encode("utf-8")
    observed_utf8 = state.observed_text.encode("utf-8")
    committed_prefix = observed_utf8[: state.committed_utf8_end]
    if committed_prefix and not final_utf8.startswith(committed_prefix):
        disposition = FinalReconciliationDisposition.REWRITE_AFTER_COMMIT
        tail = final_utf8
        correction_required = True
    elif state.committed_utf8_end == 0 and state.observed_text != final_text:
        disposition = FinalReconciliationDisposition.REWRITE_BEFORE_COMMIT
        tail = final_utf8
        correction_required = False
    else:
        disposition = FinalReconciliationDisposition.EXACT_PREFIX
        tail = final_utf8[state.committed_utf8_end :]
        correction_required = False
    return StableSentenceReconciliation(
        replace(
            state,
            active_candidate=None,
            terminal=True,
            final_text=final_text,
        ),
        disposition,
        tail,
        correction_required,
    )


__all__ = [
    "FinalReconciliationDisposition",
    "POLICY_ID",
    "StableSentenceCandidate",
    "StableSentenceCommit",
    "StableSentenceObservation",
    "StableSentenceReconciliation",
    "StableSentenceStreamState",
    "StableSentenceViolation",
    "candidate_content",
    "commit_candidate",
    "observe_agent_event",
    "reconcile_final",
]
