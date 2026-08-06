# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Idempotent Session History writer for CR-selected formal text facts."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime

from jiuwenswarm.common.schema.live_voice_contract_v2 import TurnCommit
from jiuwenswarm.server.live_voice.conversation_runtime_loop import (
    PresentationHistoryIntent,
)
from jiuwenswarm.server.live_voice.presentation_ledger import PresentationSurface
from jiuwenswarm.server.runtime.session.session_history import (
    append_formal_history_record_idempotent,
)


class FormalHistoryWriterViolation(ValueError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class SessionFormalHistoryWriter:
    """Persists only committed-user and TEXT PresentationAck intents."""

    async def persist_user(self, commit: TurnCommit, *, channel_id: str) -> bool:
        if not isinstance(commit, TurnCommit):
            raise FormalHistoryWriterViolation(
                "INVALID_FORMAL_USER_HISTORY",
                "formal user history requires a canonical TurnCommit",
            )
        session_id = commit.scope.session_id
        if not isinstance(session_id, str) or not session_id.strip():
            raise FormalHistoryWriterViolation(
                "FORMAL_HISTORY_SESSION_REQUIRED",
                "formal history requires an exact committed session scope",
            )
        timestamp = datetime.fromisoformat(
            commit.committed_at[:-1] + "+00:00"
        ).timestamp()
        record = {
            "id": f"live-voice:{commit.commit_id}:user",
            "role": "user",
            "request_id": commit.commit_id,
            "channel_id": channel_id,
            "timestamp": timestamp,
            "content": commit.text,
            "formal_binding": {
                "interaction_id": commit.interaction_id,
                "turn_id": commit.turn_id,
                "commit_id": commit.commit_id,
            },
        }
        return await asyncio.to_thread(
            append_formal_history_record_idempotent,
            session_id=session_id,
            record=record,
        )

    async def persist_assistant(
        self,
        intent: PresentationHistoryIntent,
        *,
        session_id: str,
        channel_id: str,
    ) -> tuple[bool, ...]:
        if not isinstance(intent, PresentationHistoryIntent):
            raise FormalHistoryWriterViolation(
                "INVALID_FORMAL_ASSISTANT_HISTORY",
                "assistant history requires a CR-issued intent",
            )
        if intent.surface is not PresentationSurface.TEXT:
            raise FormalHistoryWriterViolation(
                "FORMAL_HISTORY_SURFACE_FORBIDDEN",
                "Alpha formal history accepts only TEXT PresentationAck",
            )
        results: list[bool] = []
        for content in intent.contents:
            text = content.content_utf8.decode("utf-8")
            digest = hashlib.sha256(content.content_utf8).hexdigest()
            unit = content.unit
            record = {
                "id": (
                    "live-voice:"
                    f"{intent.ref.interaction_id}:{intent.ref.response_id}:"
                    f"{intent.ref.response_generation}:text:"
                    f"{intent.contiguous_cursor}:{unit.seq}:{digest}"
                ),
                "role": "assistant",
                "request_id": intent.ref.response_id,
                "channel_id": channel_id,
                "timestamp": datetime.fromisoformat(
                    intent.presented_at[:-1] + "+00:00"
                ).timestamp(),
                "content": text,
                "event_type": "chat.final",
                "formal_binding": {
                    "interaction_id": intent.ref.interaction_id,
                    "response_id": intent.ref.response_id,
                    "response_generation": intent.ref.response_generation,
                    "surface": intent.surface.value,
                    "contiguous_cursor": intent.contiguous_cursor,
                    "unit_id": unit.unit_id,
                    "unit_seq": unit.seq,
                    "source_start_utf8": unit.source_start_utf8,
                    "source_end_utf8": unit.source_end_utf8,
                    "content_ref": unit.content_ref,
                },
            }
            results.append(
                await asyncio.to_thread(
                    append_formal_history_record_idempotent,
                    session_id=session_id,
                    record=record,
                )
            )
        return tuple(results)
