# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Content-free, best-effort Gateway latency-probe operation ownership."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from jiuwenswarm.server.live_voice.latency_probe import (
    LatencyProbeContext,
    LatencyProbeRuntime,
    try_parse_latency_probe_context,
)


@dataclass(slots=True)
class GatewayLatencyProbeOperation:
    """Own one Gateway-local recorder without gaining product authority."""

    _recorder: Any
    _submit: Any
    _correlation_id: str
    _interaction_id: str
    _activation_id: str | None = None
    _activation_generation: int | None = None
    _response_id: str | None = None
    _response_generation: int | None = None
    _finished: bool = False

    @classmethod
    def create(
        cls,
        runtime: object,
        context: object,
        *,
        phase: str,
        correlation_id: str,
        interaction_id: str,
        activation_id: str | None = None,
        activation_generation: int | None = None,
        response_id: str | None = None,
        response_generation: int | None = None,
    ) -> GatewayLatencyProbeOperation | None:
        if runtime is None or context is None:
            return None
        try:
            recorder = runtime.create_recorder(
                context=context,
                phase=phase,
                clock_domain_id="gateway-process-monotonic",
                monotonic_ms=lambda: time.monotonic() * 1000.0,
            )
            submit = runtime.submit
        except Exception:
            return None
        if recorder is None or not callable(submit):
            return None
        return cls(
            recorder,
            submit,
            correlation_id,
            interaction_id,
            activation_id,
            activation_generation,
            response_id,
            response_generation,
        )

    def mark(
        self,
        point: str,
        *,
        outcome: str = "observed",
        reason_code: str | None = None,
    ) -> bool:
        if self._finished:
            return False
        try:
            return self._recorder.mark(
                point,
                correlation_id=self._correlation_id,
                interaction_id=self._interaction_id,
                activation_id=self._activation_id,
                activation_generation=self._activation_generation,
                response_id=self._response_id,
                response_generation=self._response_generation,
                outcome=outcome,
                reason_code=reason_code,
            ) is True
        except Exception:
            return False

    def finish(self, terminal_outcome: str) -> None:
        if self._finished:
            return
        self._finished = True
        try:
            batch = self._recorder.finish(terminal_outcome)
            if batch is not None:
                self._submit(batch)
        except Exception:
            return

    def abandon(self) -> None:
        """Retire a provisional operation without producing a durable shard."""

        if self._finished:
            return
        self._finished = True
        try:
            abandon = getattr(self._recorder, "abandon", None)
            if callable(abandon):
                abandon()
        except Exception:
            return


def parse_gateway_latency_probe_context(
    runtime: LatencyProbeRuntime | None,
    value: object,
) -> LatencyProbeContext | None:
    """Validate an untrusted handoff only against the enabled Gateway run."""

    if runtime is None or runtime.component != "gateway":
        return None
    try:
        return try_parse_latency_probe_context(value, runtime.run_config)
    except Exception:
        return None


__all__ = ["GatewayLatencyProbeOperation", "parse_gateway_latency_probe_context"]
