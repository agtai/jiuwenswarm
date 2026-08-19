# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Content-free, best-effort Agent Server foreground latency ownership."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseRef
from jiuwenswarm.server.live_voice.latency_probe import (
    LatencyProbeContext,
    LatencyProbeRuntime,
    try_parse_latency_probe_context,
)


@dataclass(slots=True)
class AgentForegroundLatencyProbeOperation:
    """Own one Agent-local recorder without becoming product authority."""

    _recorder: Any
    _writer: Any
    _correlation_id: str
    _interaction_id: str
    _turn_id: str
    _response_id: str | None = None
    _response_generation: int | None = None
    _task_id: str | None = None
    _finished: bool = False

    @classmethod
    def create(
        cls,
        runtime: object,
        context: object,
        *,
        correlation_id: str,
        interaction_id: str,
        turn_id: str,
    ) -> AgentForegroundLatencyProbeOperation | None:
        if runtime is None or context is None:
            return None
        try:
            recorder = runtime.create_recorder(
                context=context,
                phase="agent_foreground",
                clock_domain_id="agent-server-process-monotonic",
                monotonic_ms=lambda: time.monotonic() * 1000.0,
            )
            writer = runtime.writer
        except Exception:
            return None
        if recorder is None or not callable(getattr(writer, "write", None)):
            return None
        return cls(
            recorder,
            writer,
            correlation_id,
            interaction_id,
            turn_id,
        )

    def mark(
        self,
        point: str,
        *,
        response_ref: object | None = None,
        task_id: str | None = None,
    ) -> bool:
        if self._finished:
            return False
        if isinstance(response_ref, ResponseRef):
            if response_ref.interaction_id != self._interaction_id:
                return False
            self._response_id = response_ref.response_id
            self._response_generation = response_ref.response_generation
        if isinstance(task_id, str) and task_id:
            self._task_id = task_id
        try:
            return (
                self._recorder.mark(
                    point,
                    correlation_id=self._correlation_id,
                    interaction_id=self._interaction_id,
                    turn_id=self._turn_id,
                    response_id=self._response_id,
                    response_generation=self._response_generation,
                    task_id=self._task_id,
                )
                is True
            )
        except Exception:
            return False

    def finish(self, terminal_outcome: str) -> None:
        if self._finished:
            return
        self._finished = True
        try:
            batch = self._recorder.finish(terminal_outcome)
            if batch is not None:
                self._writer.write(batch)
        except Exception:
            return

    def abandon(self) -> None:
        """Suppress a replay/wait-only recorder without producing a shard."""

        self._finished = True


def parse_agent_latency_probe_context(
    runtime: LatencyProbeRuntime | None,
    value: object,
) -> LatencyProbeContext | None:
    """Validate an untrusted handoff only against the enabled Agent run."""

    if runtime is None or runtime.component != "agent_server":
        return None
    try:
        return try_parse_latency_probe_context(value, runtime.run_config)
    except Exception:
        return None


__all__ = [
    "AgentForegroundLatencyProbeOperation",
    "parse_agent_latency_probe_context",
]
