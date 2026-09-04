"""Passive HTTP phase observation; never retain httpcore trace info or content."""
from __future__ import annotations

import time

from jiuwenswarm.common.live_voice_audio_diagnostics import record_audio_diagnostic

_PHASES = frozenset({
    "connect_tcp", "connect_unix_socket", "start_tls", "send_request_headers",
    "send_request_body", "receive_response_headers", "receive_response_body",
    "response_closed",
})


class SpeechHttpDiagnostics:
    def __init__(self, operation_id: str, operation: str) -> None:
        self.operation_id = operation_id
        self.operation = operation
        self.started = time.monotonic()
        self.phase = "request"
        self.phase_started = self.started
        self._failed_phase: tuple[str, float] | None = None
        self._seen: set[tuple[str, str]] = set()

    def record(self, event: str, **fields: object) -> None:
        try:
            now = time.monotonic()
            phase, phase_started = self.phase, self.phase_started
            if event in {"batch_http_timeout", "batch_http_cancelled", "batch_http_transport_failed"} and self._failed_phase:
                phase, phase_started = self._failed_phase
            record_audio_diagnostic(event, operation_id=self.operation_id,
                operation=self.operation, http_phase=phase,
                elapsed_ms=(now - self.started) * 1000,
                phase_ms=(now - phase_started) * 1000, **fields)
        except Exception:
            pass

    async def trace(self, name: str, info: dict[str, object]) -> None:
        # info may contain credentials, request/response objects or exceptions.
        # Never inspect, stringify, log or save it. Bound duplicate callbacks too.
        try:
            parts = name.split(".")
            if len(parts) != 3 or parts[0] not in {"connection", "http11", "http2"}:
                return
            _, phase, outcome = parts
            if phase not in _PHASES or outcome not in {"started", "complete", "failed"}:
                return
            key = (phase, outcome)
            if key in self._seen:
                return
            self._seen.add(key)
            self.phase = phase
            if outcome == "started":
                self.phase_started = time.monotonic()
            elif outcome == "failed" and self._failed_phase is None:
                self._failed_phase = (phase, self.phase_started)
            self.record("batch_http_phase", outcome=outcome)
        except Exception:
            pass
