"""Passive local spans. No payloads, global monkey patches or business authority.

Durations belong to this process's monotonic clock. Context propagation is local
to an execution; existing identities, never new wire fields, join processes.
"""
from __future__ import annotations

import asyncio
import inspect
import re
import time
import uuid
from contextvars import ContextVar
from enum import Enum
from functools import wraps

from jiuwenswarm.common.live_voice_audio_diagnostics import record_audio_diagnostic

_CURRENT: ContextVar[dict] = ContextVar("live_voice_profile", default={})
_IDS = frozenset({
    "session_id", "media_session_id", "capture_id", "interaction_id", "correlation_id",
    "response_id", "operation_id", "request_id", "turn_id", "commit_id", "round_id",
    "task_id", "attempt_id", "command_id", "outbox_id", "unit_id", "activation_id",
    "project_id", "response_generation", "capture_generation", "activation_generation", "execution_session_id",
})
_CONTAINERS = ("scope", "binding", "ref", "response", "response_ref", "capture", "commit")


def identity_fields(*sources) -> dict:
    """Read only named identity fields and a bounded set of typed containers."""
    result = {}

    def visit(source, depth=0):
        if source is None or depth > 3:
            return
        get = source.get if isinstance(source, dict) else lambda key: getattr(source, key, None)
        for key in _IDS:
            value = get(key)
            if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", value):
                actual_key = "media_session_id" if key == "session_id" and type(source).__name__ in {
                    "RecognitionStreamRef", "SynthesisStreamRef"
                } else key
                result[actual_key] = value
            elif key.endswith("generation") and type(value) is int and 0 <= value <= 2**53 - 1:
                result[key] = value
        for name in _CONTAINERS:
            visit(get(name), depth + 1)

    for source in sources:
        try:
            visit(source)
        except Exception:
            pass
    return result


def error_fields(error) -> dict:
    """Exception class and source site only; never message, repr or locals."""
    result = {}
    try:
        result["error_type"] = type(error).__name__
        code = getattr(error, "code", None)
        if isinstance(code, Enum):
            result["error_code"] = code.name
        elif isinstance(code, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{1,119}", code):
            result["error_code"] = code
        reason = getattr(error, "reason", None)
        if isinstance(reason, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{1,119}", reason):
            result["error_reason"] = reason
        tb = getattr(error, "__traceback__", None)
        while tb is not None:
            module = tb.tb_frame.f_globals.get("__name__", "")
            if isinstance(module, str) and module.startswith("jiuwenswarm."):
                result["error_location"] = f"{module}.{tb.tb_frame.f_code.co_name}"
                result["source_line"] = tb.tb_lineno
            tb = tb.tb_next
    except Exception:
        pass
    return result


def profile_event(event, **fields):
    try:
        record_audio_diagnostic(event, **{**_CURRENT.get(), **fields})
    except Exception:
        pass


def current_profile_fields():
    return _CURRENT.get()


def profile_snapshot_event(event, snapshot, **fields):
    """Use only the captured origin, even when an async stream closes elsewhere."""
    try:
        record_audio_diagnostic(event, _inherit_context=False, **{**snapshot, **fields})
    except Exception:
        pass


def profile_tool_event(payload, **identity):
    """Every observed tool boundary; absent call IDs are never paired by order."""
    try:
        kind = payload.get("event_type")
        if kind not in {"chat.tool_call", "chat.tool_result"}:
            return
        carrier = payload.get("tool_call", {}) if kind == "chat.tool_call" else payload
        call_id = carrier.get("tool_call_id") or carrier.get("toolCallId") or carrier.get("id")
        outcome = "unknown"
        if kind == "chat.tool_result":
            if payload.get("success") is False or payload.get("is_error") is True:
                outcome = "failed"
            elif payload.get("success") is True:
                outcome = "complete"
        profile_event("tool_boundary", **identity, milestone=kind,
                      tool_call_id=call_id, tool_name=carrier.get("tool_name") or carrier.get("name"),
                      outcome=outcome, diagnostic_complete=isinstance(call_id, str) and bool(call_id))
    except Exception:
        pass


class ProfileSpan:
    def __init__(self, stage, **fields):
        self.stage = stage
        self.fields = fields
        self.token = None
        self.started = None
        self.outcome = "returned"

    def __enter__(self):
        try:
            parent = _CURRENT.get()
            self.fields = {**parent, **self.fields, "stage": self.stage,
                           "span_id": uuid.uuid4().hex,
                           "parent_span_id": parent.get("span_id", "")}
            self.started = time.perf_counter()
            self.token = _CURRENT.set(self.fields)
            profile_event("profile_span_started", outcome="started")
        except Exception:
            pass
        return self

    def result(self, result):
        """Returned != business success. Observe an explicit rejected envelope."""
        try:
            get = result.get if isinstance(result, dict) else lambda key: getattr(result, key, None)
            if get("ok") is False:
                self.outcome = "rejected"
                error = get("error")
                payload = get("payload")
                if not isinstance(error, dict) and isinstance(payload, dict):
                    error = payload.get("error")
                if isinstance(error, dict):
                    for name in ("code", "reason"):
                        value = error.get(name)
                        if isinstance(value, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{1,119}", value):
                            self.fields["error_" + name] = value
            status = get("status")
            if isinstance(status, Enum):
                self.fields["result_state"] = status.name
            self.fields.update(identity_fields(result))
        except Exception:
            pass
        return result

    def __exit__(self, exc_type, exc, tb):
        try:
            outcome = self.outcome
            if exc is not None:
                outcome = "cancelled" if isinstance(exc, (asyncio.CancelledError, GeneratorExit)) else (
                    "timeout" if isinstance(exc, TimeoutError) else "failed")
            record_audio_diagnostic("profile_span_settled", **{**self.fields,
                "outcome": outcome,
                "duration_ms": None if self.started is None else (time.perf_counter() - self.started) * 1000,
                **(error_fields(exc) if exc is not None else {})})
        except Exception:
            pass
        finally:
            if self.token is not None:
                try:
                    _CURRENT.reset(self.token)
                except Exception:
                    pass
        return False


def profiled(stage, *identity_arguments, require_context=False):
    """Explicit async function boundary; observes exactly one existing call."""
    def decorate(function):
        signature = inspect.signature(function)

        @wraps(function)
        async def observed(*args, **kwargs):
            if require_context and not _CURRENT.get():
                return await function(*args, **kwargs)
            fields = {}
            try:
                bound = signature.bind(*args, **kwargs).arguments
                sources = []
                for path in identity_arguments:
                    head, *tail = path.split(".")
                    source = bound.get(head)
                    for key in tail:
                        source = source.get(key) if isinstance(source, dict) else getattr(source, key, None)
                    sources.append(source)
                fields = identity_fields({key: bound.get(key) for key in _IDS}, *sources)
            except Exception:
                pass
            with ProfileSpan(stage, **fields) as span:
                return span.result(await function(*args, **kwargs))
        if inspect.iscoroutinefunction(function):
            return observed

        @wraps(function)
        def observed_sync(*args, **kwargs):
            if require_context and not _CURRENT.get():
                return function(*args, **kwargs)
            with ProfileSpan(stage) as span:
                return span.result(function(*args, **kwargs))
        return observed_sync
    return decorate
