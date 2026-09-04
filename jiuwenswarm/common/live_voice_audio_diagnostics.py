"""Bounded passive audio diagnostics, never raw payloads or an authority rail."""
from __future__ import annotations

import json
import logging
import math
import os
import queue
import re
import threading
import time
import uuid
from itertools import count
from datetime import UTC, datetime

_LOGGER = logging.getLogger(__name__)
_QUEUE: queue.Queue[str] = queue.Queue(maxsize=256)
_START_LOCK = threading.Lock()
_WORKER: threading.Thread | None = None
_DROPPED = 0
_CLOCK_ID = f"python-{os.getpid()}-{uuid.uuid4().hex[:12]}"
_SEQUENCE = count(1)
# JSON strings are consumed whole so numeric-looking identifiers are never
# rewritten. Only numeric tokens outside strings use the alternate notation.
_JSON_TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)')


def _encode_record(value: dict) -> str:
    """Keep JSON numbers exact and parseable through the standard PII filter.

    Scientific JSON notation can split long digit runs without disabling the
    filter or turning numbers into strings. Up to 18 significant digits cover
    binary64 floats and safe integer counters; larger numbers fail open at the
    caller instead of generating potentially malformed diagnostic evidence.
    """
    def number(match: re.Match) -> str:
        raw = match.group(1)
        if raw is None or not re.search(r"\d{11}", raw):
            return match.group(0)
        mantissa, _, exponent = raw.lower().partition("e")
        whole, _, fraction = mantissa.lstrip("-").partition(".")
        digits = (whole + fraction).lstrip("0") or "0"
        if len(digits) > 18:
            raise ValueError("diagnostic numeric precision bound")
        split = min(9, len(digits))
        power = int(exponent or "0") - len(fraction) + len(digits) - split
        sign = "-" if raw.startswith("-") else ""
        return f"{sign}{digits[:split]}.{digits[split:] or '0'}e{power}"

    return _JSON_TOKEN.sub(number, json.dumps(value, separators=(",", ":")))


_IDS = frozenset({"session_id", "media_session_id", "capture_id", "lease_id", "interaction_id", "correlation_id", "response_id", "operation_id", "request_id"})
_IDS = _IDS | frozenset({"span_id", "model_call_id", "parent_span_id", "turn_id", "commit_id", "round_id", "task_id", "attempt_id", "command_id", "outbox_id", "tool_call_id", "unit_id", "activation_id", "project_id", "execution_session_id"})
_TOKENS = frozenset({"stage", "rpc_method", "error_type", "error_location", "error_code", "error_reason", "result_state", "milestone", "tool_name"})
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
    "model_call_seq", "message_count", "user_message_count", "current_envelope_count",
    "current_envelope_in_last_user", "diagnostic_complete", "output_chars",
    "repeats_selected_assistant", "audio_bytes", "audio_duration_ms", "sample_rate_hz",
    "channels", "sample_width_bytes",
    "duration_ms", "response_generation", "activation_generation", "capture_generation",
    "first_output_ms", "chunk_count", "max_chunk_gap_ms", "attempt_number", "tool_seq",
    "source_line", "diagnostic_sequence", "queue_wait_ms", "event_count",
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
    "outcome": frozenset({"started", "complete", "failed", "cancelled", "timeout", "returned", "rejected", "fallback", "unknown", "skipped"}),
    "operation": frozenset({"speech.recognize.batch", "speech.synthesize.batch", "speech.synthesize.stream"}),
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


def record_audio_diagnostic(event: str, *, _inherit_context: bool = True, **fields: object) -> None:
    """Drop on overload/sink failure; the event loop never waits for disk I/O."""
    global _WORKER, _DROPPED, _SEQUENCE
    try:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", event):
            return
        from jiuwenswarm.common.live_voice_profiling import current_profile_fields
        fields = {**(current_profile_fields() if _inherit_context else {}), **fields}
        safe: dict[str, object] = {}
        for key, value in fields.items():
            if key in _IDS and isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", value):
                safe[key] = value
            elif key in _VALUES and (value is None or type(value) is bool or (type(value) in {int, float} and math.isfinite(value))):
                # Sub-millisecond precision is sufficient for these observations.
                # Long decimal tails can match the standard log PII filter's
                # phone pattern and turn a JSON number into invalid `0.******`.
                # Keep that filter enabled; bound numeric precision at the sink.
                safe[key] = round(value, 3) if type(value) is float else value
            elif key in _LABELS and isinstance(value, str) and value in _LABELS[key]:
                safe[key] = value
            elif key in _TOKENS and isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", value):
                safe[key] = value
        item = _encode_record({"event": event, "observed_at": datetime.now(UTC).isoformat(),
            "monotonic_ms": round(time.perf_counter() * 1000, 3), "clock_id": _CLOCK_ID,
            "sequence": next(_SEQUENCE), "dropped_records": _DROPPED, "fields": safe})
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
