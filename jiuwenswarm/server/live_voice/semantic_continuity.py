# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Bounded pre-command data continuity; no Task/Tool/confirmation authority."""

from __future__ import annotations

from jiuwenswarm.common.live_voice_profiling import profiled

import asyncio
import hashlib
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ErrorCode,
    ResponseRef,
    ScopeRef,
    TurnCommit,
    canonical_json_bytes,
)
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
    PresentedAgentAnalysis,
)

from .formal_task_models import FormalTaskViolation
from .task_semantics import TaskSemanticDecision
from .unified_committed_input import (
    SEMANTIC_PROPOSAL_TTL_SECONDS,
    PendingSemanticContext,
    SqliteUnifiedCommittedInputJournal,
)


SemanticCall = Callable[..., Awaitable[TaskSemanticDecision]]


def _fail(reason: str) -> FormalTaskViolation:
    return FormalTaskViolation(
        reason, "semantic continuity unavailable", ErrorCode.CONFLICT
    )


class SemanticContinuity:
    """One Registry-owned, bounded coordinator over the existing journal.

    Resolver callbacks must authenticate the exact scope before Provider access.
    Captured credentials stay in the caller's short-lived owned coroutine, never
    in persisted payloads. Reconnect can resume source extraction, not permission.
    """

    def __init__(self, journal: SqliteUnifiedCommittedInputJournal) -> None:
        self.journal = journal
        self._locks: dict[bytes, tuple[asyncio.Lock, int]] = {}

    async def retain_analysis(
        self, analysis: PresentedAgentAnalysis
    ) -> PendingSemanticContext:
        payload = {
            "commit": analysis.commit.to_dict(),
            "response": {
                "interaction_id": analysis.response.interaction_id,
                "response_id": analysis.response.response_id,
                "response_generation": analysis.response.response_generation,
            },
            "text": analysis.text,
            "presented_at": analysis.presented_at,
        }
        existing = await asyncio.to_thread(
            self.journal.find_semantic_context,
            scope=analysis.commit.scope,
            kind="analysis",
            source_id=analysis.source_id,
        )
        if existing is not None:
            if canonical_json_bytes(existing.payload) != canonical_json_bytes(payload):
                raise _fail("SEMANTIC_CONTEXT_SOURCE_CONFLICT")
            return existing
        issued = datetime.fromisoformat(
            analysis.presented_at.replace("Z", "+00:00")
        ).timestamp()
        return await asyncio.to_thread(
            self.journal.retain_semantic_context,
            scope=analysis.commit.scope,
            kind="analysis",
            source_id=analysis.source_id,
            payload=payload,
            issued_at=issued,
            expires_at=issued + SEMANTIC_PROPOSAL_TTL_SECONDS,
        )

    async def finish_analyses(self, scope: ScopeRef, resolve: SemanticCall) -> None:
        key = canonical_json_bytes(scope.to_dict())
        if key not in self._locks and len(self._locks) >= 32:
            raise _fail("SEMANTIC_ANALYSIS_CAPACITY_EXCEEDED")
        lock, users = self._locks.get(key, (asyncio.Lock(), 0))
        self._locks[key] = (lock, users + 1)
        try:
            async with lock:
                records = await asyncio.to_thread(
                    self.journal.read_semantic_contexts, scope=scope
                )
                for record in records:
                    if record.kind != "analysis":
                        continue
                    payload = record.payload
                    if set(payload) != {"commit", "response", "text", "presented_at"}:
                        raise _fail("SEMANTIC_ANALYSIS_CORRUPT")
                    analysis = PresentedAgentAnalysis(
                        TurnCommit.from_dict(payload["commit"]),
                        ResponseRef(**payload["response"]),
                        payload["text"],
                        payload["presented_at"],
                    )
                    if (
                        analysis.commit.scope != scope
                        or analysis.source_id != record.source_id
                    ):
                        raise _fail("SEMANTIC_ANALYSIS_SCOPE_MISMATCH")
                    prior = await asyncio.to_thread(
                        self.journal.find_semantic_context,
                        scope=scope,
                        kind="proposal",
                        source_id=record.source_id,
                    )
                    if prior is None:
                        decision = await resolve(
                            commit=analysis.commit,
                            history=(),
                            pending=(),
                            analysis={
                                "source_id": record.source_id,
                                "text": analysis.text,
                            },
                        )
                        if decision.route == "proposal":
                            await asyncio.to_thread(
                                self.journal.retain_semantic_context,
                                scope=scope,
                                kind="proposal",
                                source_id=record.source_id,
                                payload={
                                    "operation": decision.proposal.operation,
                                    "target": decision.proposal.target,
                                    "target_kind": decision.proposal.target_kind,
                                    "arguments": dict(decision.proposal.arguments),
                                    "semantic_context_binding": decision.origin_context_binding,
                                },
                                issued_at=record.issued_at,
                                expires_at=record.expires_at,
                            )
                    await asyncio.to_thread(
                        self.journal.consume_semantic_context,
                        scope=scope,
                        context_id=record.context_id,
                        version=record.version,
                        commit_sha256=hashlib.sha256(
                            analysis.commit.canonical_bytes()
                        ).hexdigest(),
                    )
        finally:
            current, users = self._locks[key]
            if users == 1:
                del self._locks[key]
            else:
                self._locks[key] = (current, users - 1)

    @profiled('semantic.pending', 'scope')
    async def pending(self, scope: ScopeRef) -> tuple[Mapping[str, object], ...]:
        records = await asyncio.to_thread(
            self.journal.read_semantic_contexts, scope=scope
        )
        return tuple(
            self.pending_entry(record)
            for record in records
            if record.kind != "analysis"
        )

    @profiled('semantic.history', 'scope')
    async def history(
        self, scope: ScopeRef, *, committed: tuple[TurnCommit, ...] = ()
    ) -> tuple[Mapping[str, object], ...]:
        records = await asyncio.to_thread(
            self.journal.read_semantic_analysis_history, scope=scope
        )
        groups: dict[str, tuple[str, tuple[Mapping[str, object], ...]]] = {}
        for commit in committed:
            if not isinstance(commit, TurnCommit) or commit.scope != scope:
                raise _fail("SEMANTIC_ANALYSIS_SCOPE_MISMATCH")
            groups[commit.commit_id] = (commit.committed_at, (
                {"role": "user", "text": commit.text, "source_id": commit.commit_id},
            ))
        for record in records:
            commit = TurnCommit.from_dict(record.payload["commit"])
            text = record.payload["text"]
            if commit.scope != scope or type(text) is not str:
                raise _fail("SEMANTIC_ANALYSIS_SCOPE_MISMATCH")
            pair = (
                {"role": "user", "text": commit.text, "source_id": commit.commit_id},
                {"role": "assistant", "text": text, "source_id": record.source_id},
            )
            groups[commit.commit_id] = (commit.committed_at, pair)
        result: list[Mapping[str, object]] = []
        total = 0
        for _, pair in sorted(groups.values(), key=lambda group: group[0], reverse=True):
            if len(result) + len(pair) > 32:
                break
            if any(len(entry["text"].encode("utf-8")) > 8_192 for entry in pair):
                continue
            size = len(canonical_json_bytes(list(pair)))
            if total + size > 49_152:
                break
            result[0:0] = pair
            total += size
        return tuple(result)

    @staticmethod
    def pending_entry(record: PendingSemanticContext) -> Mapping[str, object]:
        payload = record.payload
        if record.kind not in {"proposal", "confirmation", "clarification"}:
            raise _fail("SEMANTIC_PENDING_INVALID")
        return {
            "id": record.context_id,
            "version": record.version,
            "kind": record.kind,
            "operation": payload["operation"],
            "target": payload["target"],
            "target_kind": payload["target_kind"],
            "arguments": payload["arguments"],
            # The existing structured UI may name this opaque continuation in
            # user input. It is a reference alias only, not a confirmation grant;
            # exact source provenance stays in the journal and formal binding.
            "source_id": payload.get("token", record.source_id),
        }

    async def reference(
        self, decision: TaskSemanticDecision, commit: TurnCommit
    ) -> PendingSemanticContext | None:
        if decision.reference_id is None:
            return None
        return await asyncio.to_thread(
            self.journal.read_semantic_reference,
            scope=commit.scope,
            context_id=decision.reference_id,
            version=decision.reference_version,
            commit_sha256=hashlib.sha256(commit.canonical_bytes()).hexdigest(),
        )

    async def consume(self, record: PendingSemanticContext, commit: TurnCommit) -> None:
        await asyncio.to_thread(
            self.journal.consume_semantic_context,
            scope=commit.scope,
            context_id=record.context_id,
            version=record.version,
            commit_sha256=hashlib.sha256(commit.canonical_bytes()).hexdigest(),
        )
