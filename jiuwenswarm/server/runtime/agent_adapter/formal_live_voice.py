# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Immutable inputs for the Live Voice formal Agent execution seam."""

from __future__ import annotations

import json
from dataclasses import dataclass

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ContextRef,
    ScopeRef,
    TurnCommit,
    canonical_json_bytes,
)


FORMAL_APPEND_ONLY_DELTA_CAPABILITY = "agent.chat.append_only_delta.v1"


class FormalLiveVoiceViolation(ValueError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FormalLiveVoiceViolation(
            "INVALID_FORMAL_AGENT_INPUT",
            f"{field_name} must be a non-empty string",
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise FormalLiveVoiceViolation(
            "INVALID_FORMAL_AGENT_INPUT",
            f"{field_name} must contain only Unicode scalar values",
        ) from error
    return value


@dataclass(frozen=True, slots=True)
class FormalContextEntry:
    """One CR-selected context value and its immutable source reference."""

    ref: ContextRef
    content: str

    def __post_init__(self) -> None:
        if not isinstance(self.ref, ContextRef):
            raise FormalLiveVoiceViolation(
                "INVALID_FORMAL_CONTEXT",
                "formal context entries require canonical ContextRef values",
            )
        _require_text(self.content, "context.content")


@dataclass(frozen=True, slots=True)
class FormalContextSnapshot:
    """The complete, explicit context selected by CR for one committed turn."""

    scope: ScopeRef
    entries: tuple[FormalContextEntry, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ScopeRef):
            raise FormalLiveVoiceViolation(
                "INVALID_FORMAL_CONTEXT",
                "formal context requires a canonical ScopeRef",
            )
        if not isinstance(self.entries, tuple):
            raise FormalLiveVoiceViolation(
                "INVALID_FORMAL_CONTEXT",
                "formal context entries must be an immutable tuple",
            )
        seen: set[bytes] = set()
        for entry in self.entries:
            if not isinstance(entry, FormalContextEntry):
                raise FormalLiveVoiceViolation(
                    "INVALID_FORMAL_CONTEXT",
                    "formal context contains an unsupported entry",
                )
            if entry.ref.scope != self.scope:
                raise FormalLiveVoiceViolation(
                    "FORMAL_CONTEXT_SCOPE_MISMATCH",
                    "formal context cannot cross the committed scope",
                )
            fingerprint = canonical_json_bytes(entry.ref.to_dict())
            if fingerprint in seen:
                raise FormalLiveVoiceViolation(
                    "FORMAL_CONTEXT_DUPLICATE",
                    "formal context cannot repeat the same source reference",
                )
            seen.add(fingerprint)

    def validate_for(self, commit: TurnCommit) -> None:
        if not isinstance(commit, TurnCommit):
            raise FormalLiveVoiceViolation(
                "INVALID_FORMAL_AGENT_INPUT",
                "formal execution requires a canonical TurnCommit",
            )
        if commit.scope != self.scope:
            raise FormalLiveVoiceViolation(
                "FORMAL_CONTEXT_SCOPE_MISMATCH",
                "selected context must match the committed turn scope",
            )
        allowed = {canonical_json_bytes(ref.to_dict()) for ref in commit.context_refs}
        for entry in self.entries:
            if canonical_json_bytes(entry.ref.to_dict()) not in allowed:
                raise FormalLiveVoiceViolation(
                    "FORMAL_CONTEXT_NOT_COMMITTED",
                    "selected context must be backed by the committed context_refs",
                )


@dataclass(frozen=True, slots=True)
class FormalAgentExecution:
    """A committed-turn-only request for the facade's no-history path."""

    request_id: str
    channel_id: str
    internal_session_id: str
    commit: TurnCommit
    context: FormalContextSnapshot
    allow_tools: bool = True

    def __post_init__(self) -> None:
        _require_text(self.request_id, "request_id")
        _require_text(self.channel_id, "channel_id")
        _require_text(self.internal_session_id, "internal_session_id")
        if not isinstance(self.commit, TurnCommit):
            raise FormalLiveVoiceViolation(
                "INVALID_FORMAL_AGENT_INPUT",
                "formal execution requires a canonical TurnCommit",
            )
        if type(self.allow_tools) is not bool:
            raise FormalLiveVoiceViolation(
                "INVALID_FORMAL_AGENT_INPUT",
                "formal execution tool policy must be a boolean",
            )
        self.context.validate_for(self.commit)

    def prompt_content(self) -> str:
        """Build only from the committed text and the explicit CR snapshot."""

        selected = [
            {
                "context_ref": entry.ref.to_dict(),
                "content": entry.content,
            }
            for entry in self.context.entries
        ]
        return json.dumps(
            {
                "source": "live_voice.formal",
                "selected_context": selected,
                "committed_turn": {
                    "commit_id": self.commit.commit_id,
                    "turn_id": self.commit.turn_id,
                    "text": self.commit.text,
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
