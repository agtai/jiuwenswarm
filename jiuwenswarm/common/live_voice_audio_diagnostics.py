"""Bounded passive audio diagnostics, never raw payloads or an authority rail."""
from __future__ import annotations

import json
import logging
import math
import queue
import re
import threading
import time
from datetime import UTC, datetime

_LOGGER = logging.getLogger(__name__)
_QUEUE: queue.Queue[str] = queue.Queue(maxsize=256)
_START_LOCK = threading.Lock()
_WORKER: threading.Thread | None = None
_DROPPED = 0
_IDS = frozenset({"session_id", "media_session_id", "capture_id", "lease_id", "interaction_id", "correlation_id", "response_id", "operation_id"})
_VALUES = frozenset({"generation", "frame_count", "frames_sent", "frames_acked", "queue_frames", "received_samples", "sent_sample_end", "send_peak_ms", "vad_silence_ms", "provider_ms", "provider_start_ms", "provider_end_ms", "speech_started", "input_fenced", "elapsed_ms", "preopen_frames"})
_VALUES = _VALUES | frozenset({
    "frame_seq", "lock_wait_ms", "encode_ms", "socket_send_ms", "wire_seq",
    "wire_bytes", "event_queue_frames", "event_seq", "committed", "closing",
    "terminal", "item_matches_speech", "item_matches_committed", "has_item",
    "speech_stopped", "timeout_ms", "status_code", "response_bytes", "phase_ms",
    "write_buffer_bytes", "write_buffer_low_bytes", "write_buffer_high_bytes",
    "write_buffer_peak_bytes", "transport_paused", "write_pause_ms", "drain_ms",
    "loop_lag_ms", "loop_lag_peak_ms", "peer_loopback", "flow_observer",
    "oldest_queue_age_ms", "frame_queue_wait_ms", "pending_audio_ms",
    "observation_expired",
})
WIRE_EVENTS = frozenset({
    "session.updated", "transcription_session.updated", "session.created",
    "transcription_session.created", "input_audio_buffer.speech_started",
    "input_audio_buffer.speech_stopped", "input_audio_buffer.committed",
    "conversation.item.input_audio_transcription.delta",
    "conversation.item.input_audio_transcription.completed",
    "conversation.item.input_audio_transcription.failed", "error",
    "conversation.item.created", "conversation.item.added", "conversation.item.done",
    "rate_limits.updated", "other", "unparsed", "receive_wait",
})
FAILURE_CODES = frozenset({
    "other", "cancelled", "SPEECH_PROVIDER_TIMEOUT",
    "SPEECH_PROVIDER_TRANSPORT_UNAVAILABLE", "SPEECH_PROVIDER_BINARY_CONTROL",
    "SPEECH_PROVIDER_MESSAGE_LIMIT", "SPEECH_PROVIDER_INVALID_JSON",
    "SPEECH_PROVIDER_SESSION_MISMATCH", "SPEECH_PROVIDER_TURN_ORDER",
    "SPEECH_PROVIDER_INVALID_IDENTITY", "SPEECH_PROVIDER_INVALID_TIMING",
    "SPEECH_PROVIDER_INVALID_TEXT", "SPEECH_PROVIDER_CONTENT_MISMATCH",
    "SPEECH_PROVIDER_ITEM_MISMATCH", "SPEECH_PROVIDER_PRECOMMIT_OUTPUT",
    "SPEECH_PROVIDER_RECOGNITION_FAILED", "SPEECH_PROVIDER_UNKNOWN_EVENT",
    "SPEECH_PROVIDER_CURSOR_UNAVAILABLE", "SPEECH_EVENT_QUEUE_EXHAUSTED",
    "RECOGNITION_INPUT_FENCED", "RECOGNITION_OUTPUT_FENCED",
    "RECOGNITION_ALREADY_TERMINAL", "RECOGNITION_EVENT_GAP",
    "DUPLICATE_RECOGNITION_EVENT", "RECOGNITION_PROVIDER_MISMATCH",
    "RECOGNITION_CAPTURE_MISMATCH", "STALE_RECOGNITION_SESSION",
    "RECOGNITION_STREAM_TIMEOUT", "RECOGNITION_SESSION_NOT_FOUND",
    "RECOGNITION_EVENT_SEQUENCE_EXHAUSTED", "INVALID_RECOGNITION_EVENT",
    "INVALID_RECOGNITION_AUDIO_CURSOR", "UNPROVEN_RECOGNITION_TIMING",
    "INVALID_TURN_BOUNDARY", "TURN_BOUNDARY_UNNEGOTIATED", "INVALID_TURN_BOUNDARY_ORDER",
    "INVALID_TURN_BOUNDARY_TIME", "INVALID_TURN_BOUNDARY_TIMING",
    "SPEECH_AUTHORITY_REQUIRED", "SPEECH_AUTHORITY_EXPIRED", "SPEECH_AUTHORITY_CONSUMED",
    "EMPTY_RECOGNITION_AUDIO_RANGE", "INVALID_RECOGNITION_EVENT_KIND",
    "UNPROVEN_RECOGNITION_CANCEL_ACK", "CANCELLED_HYPOTHESIS_FORBIDDEN",
})
_LABELS = {
    "proxy_route_hint": frozenset({"direct", "http", "https", "socks5", "socks5h", "socks4", "socks4a", "unknown"}),
    "wire_event": WIRE_EVENTS,
    "failure_code": FAILURE_CODES,
    "commit_owner": frozenset({"none", "manual", "server_vad"}),
    "outcome": frozenset({"started", "complete", "failed", "cancelled", "timeout"}),
    "operation": frozenset({"speech.recognize.batch", "speech.synthesize.batch"}),
    "http_phase": frozenset({"request", "connect_tcp", "connect_unix_socket", "start_tls",
        "send_request_headers", "send_request_body", "receive_response_headers",
        "receive_response_body", "response_closed"}),
    "timeout_kind": frozenset({"connect", "read", "write", "pool", "other"}),
}


def _run() -> None:
    while True:
        item = _QUEUE.get()
        try:
            _LOGGER.info("live_voice_audio_diagnostic %s", item)
        except BaseException:
            pass
        finally:
            _QUEUE.task_done()


def record_audio_diagnostic(event: str, **fields: object) -> None:
    """Drop on overload/sink failure; the event loop never waits for disk I/O."""
    global _WORKER, _DROPPED
    try:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", event):
            return
        safe: dict[str, object] = {}
        for key, value in fields.items():
            if key in _IDS and isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", value):
                safe[key] = value
            elif key in _VALUES and (value is None or type(value) is bool or (type(value) in {int, float} and math.isfinite(value))):
                safe[key] = value
            elif key in _LABELS and isinstance(value, str) and value in _LABELS[key]:
                safe[key] = value
        item = json.dumps({"event": event, "observed_at": datetime.now(UTC).isoformat(),
            "monotonic_ms": time.monotonic() * 1000, "dropped_records": _DROPPED, "fields": safe}, separators=(",", ":"))
        if _WORKER is None:
            with _START_LOCK:
                if _WORKER is None:
                    _WORKER = threading.Thread(target=_run, name="live-voice-audio-diagnostics", daemon=True)
                    _WORKER.start()
        try:
            _QUEUE.put_nowait(item)
        except queue.Full:
            _DROPPED += 1
    except Exception:
        pass
