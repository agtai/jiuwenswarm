# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Committed-turn-only asynchronous Agent bridge port."""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

from jiuwenswarm.common.schema.live_voice_contract_v2 import TurnCommit, canonical_json


class AgentBridgeViolation(ValueError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class AgentRequest:
    request_id: str
    interaction_id: str
    turn_id: str
    commit_id: str
    text: str
    source_provenance: str


@dataclass(frozen=True, slots=True)
class AgentEvent:
    request_id: str
    interaction_id: str
    turn_id: str
    commit_id: str
    seq: int
    event_type: str
    source_provenance: str
    text: str | None = None
    capability: str | None = None
    error_reason: str | None = None


class AgentHandler(Protocol):
    def __call__(self, request: AgentRequest) -> tuple[AgentEvent, ...]: ...


class AgentBridgePort:
    def __init__(self, *, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.RLock()
        self._requests: dict[str, Future[tuple[AgentEvent, ...]]] = {}
        self._fingerprints: dict[str, bytes] = {}

    def submit(
        self, request_id: str, commit: TurnCommit, handler: AgentHandler
    ) -> tuple[bool, Future[tuple[AgentEvent, ...]]]:
        if not request_id.strip():
            raise AgentBridgeViolation(
                "INVALID_REQUEST_ID", "request_id must be non-empty"
            )
        fingerprint = commit.canonical_bytes()
        with self._lock:
            existing = self._requests.get(request_id)
            if existing is not None:
                if self._fingerprints[request_id] == fingerprint:
                    return False, existing
                raise AgentBridgeViolation(
                    "REQUEST_ID_CONFLICT", "request_id cannot change its commit"
                )
            request = AgentRequest(
                request_id=request_id,
                interaction_id=commit.interaction_id,
                turn_id=commit.turn_id,
                commit_id=commit.commit_id,
                text=commit.text,
                source_provenance=canonical_json(commit.hypothesis_provenance),
            )
            future = self._executor.submit(self._invoke, request, handler)
            self._requests[request_id] = future
            self._fingerprints[request_id] = fingerprint
            return True, future

    @staticmethod
    def _invoke(request: AgentRequest, handler: AgentHandler) -> tuple[AgentEvent, ...]:
        events = handler(request)
        for expected, event in enumerate(events):
            if (
                event.request_id != request.request_id
                or event.interaction_id != request.interaction_id
                or event.turn_id != request.turn_id
                or event.commit_id != request.commit_id
                or event.seq != expected
                or event.source_provenance != request.source_provenance
            ):
                raise AgentBridgeViolation(
                    "INVALID_AGENT_EVENT_PROVENANCE",
                    "Agent events must preserve identity and contiguous sequence",
                )
        return tuple(events)

    def close(self) -> None:
        self._executor.shutdown(wait=True)
