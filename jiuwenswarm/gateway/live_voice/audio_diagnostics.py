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
_IDS = frozenset({"session_id", "media_session_id", "capture_id", "lease_id", "interaction_id", "correlation_id", "response_id"})
_VALUES = frozenset({"generation", "frame_count", "frames_sent", "frames_acked", "queue_frames", "received_samples", "sent_sample_end", "send_peak_ms", "vad_silence_ms", "provider_ms", "provider_start_ms", "provider_end_ms", "speech_started", "input_fenced", "elapsed_ms", "preopen_frames"})


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
