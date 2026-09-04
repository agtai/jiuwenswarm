"""Content-free observation at the isolated formal Model's client boundary.

No prompt, output or content hash is exported. Equality facts distinguish a
missing current envelope from a new model answer repeating selected history.
The wrapper never edits arguments, retries calls or creates model authority.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from contextlib import aclosing, nullcontext

from jiuwenswarm.common.live_voice_audio_diagnostics import record_audio_diagnostic
from jiuwenswarm.common.live_voice_profiling import ProfileSpan, current_profile_fields, error_fields, profile_snapshot_event

_MAX_CALLS = 16
_MAX_MESSAGES = 256
_MAX_TEXT = 1_000_000


def _get(value, key, default=None):
    return (
        value.get(key, default)
        if isinstance(value, dict)
        else getattr(value, key, default)
    )


class FormalModelDiagnostics:
    def __init__(self, client, *, envelope: str, request_id: str, session_id: str):
        self._client = client
        self._envelope = envelope if len(envelope) <= _MAX_TEXT else ""
        self._ids = {"request_id": request_id,
                     "execution_session_id" if session_id.startswith("lv-formal-") else "session_id": session_id}
        self._sequence = 0
        self._previous_answers: set[bytes] = set()
        try:
            payload = json.loads(self._envelope)
            for entry in payload.get("selected_context", [])[:32]:
                if (
                    entry.get("context_ref", {}).get("source")
                    == "live_voice.cr_presented_assistant"
                ):
                    content = entry.get("content")
                    if isinstance(content, str):
                        self._previous_answers.add(
                            hashlib.sha256(content.encode()).digest()
                        )
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._client, name)

    def _record(self, event, seq, *, origin_context=None, **fields):
        try:
            if seq <= _MAX_CALLS or event in {"formal_model_first_output", "formal_model_stream_gap"}:
                record_audio_diagnostic(
                    event, _inherit_context=origin_context is None,
                    **{**(origin_context or {}), **self._ids, "model_call_seq": seq, **fields}
                )
        except Exception:
            pass

    def _begin(self, args, kwargs):
        self._sequence += 1
        seq = self._sequence
        started = time.perf_counter()
        if seq > _MAX_CALLS:
            return seq, started
        try:
            messages = kwargs.get("messages", args[0] if args else None)
            messages = [messages] if isinstance(messages, str) else messages
            users = []
            complete = (
                isinstance(messages, (list, tuple)) and len(messages) <= _MAX_MESSAGES
            )
            budget = _MAX_TEXT
            if isinstance(messages, (list, tuple)):
                for message in messages[:_MAX_MESSAGES]:
                    role = _get(
                        message, "role", "user" if isinstance(message, str) else None
                    )
                    if getattr(role, "value", role) == "user":
                        content = (
                            message
                            if isinstance(message, str)
                            else _get(message, "content")
                        )
                        if isinstance(content, str) and len(content) <= budget:
                            users.append(content)
                            budget -= len(content)
                        else:
                            complete = False
            matches = [
                bool(self._envelope and self._envelope in content) for content in users
            ]
            self._record(
                "formal_model_request",
                seq,
                message_count=len(messages)
                if isinstance(messages, (list, tuple))
                else None,
                user_message_count=len(users),
                current_envelope_count=sum(matches),
                current_envelope_in_last_user=matches[-1] if matches else False,
                diagnostic_complete=complete and bool(self._envelope),
            )
        except Exception:
            self._record("formal_model_request", seq, diagnostic_complete=False)
        return seq, started

    async def invoke(self, *args, **kwargs):
        seq, started = self._begin(args, kwargs)
        try:
            with ProfileSpan("model.invoke", **self._ids, model_call_seq=seq):
                result = await self._client.invoke(*args, **kwargs)
        except BaseException as error:
            self._record(
                "formal_model_result",
                seq,
                outcome="cancelled"
                if isinstance(error, asyncio.CancelledError)
                else "failed",
                elapsed_ms=(time.perf_counter() - started) * 1000,
            )
            raise
        try:
            self._output(seq, started, _get(result, "content"))
        except Exception:
            self._record(
                "formal_model_result",
                seq,
                outcome="complete",
                diagnostic_complete=False,
            )
        return result

    def _output(self, seq, started, content):
        try:
            known = isinstance(content, str) and len(content) <= _MAX_TEXT
            self._record(
                "formal_model_result",
                seq,
                outcome="complete",
                elapsed_ms=(time.perf_counter() - started) * 1000,
                output_chars=len(content) if known else None,
                repeats_selected_assistant=(
                    hashlib.sha256(content.encode()).digest() in self._previous_answers
                )
                if known
                else None,
            )
        except Exception:
            pass

    async def stream(self, *args, **kwargs):
        seq, started = self._begin(args, kwargs)
        timing_ids = {**current_profile_fields(), **self._ids}
        # Detailed content-equality inspection keeps its existing bound; timing
        # metadata remains available for every model call in a long rehearsal.
        model_call_id = uuid.uuid4().hex
        profile_snapshot_event("model_stream_started", timing_ids, model_call_id=model_call_id, model_call_seq=seq, outcome="started")
        digest = hashlib.sha256()
        chars = 0
        known = True
        chunk_count = 0
        last_chunk_at = started
        max_gap_ms = 0.0
        first_output_ms = None
        try:
            raw_stream = self._client.stream(*args, **kwargs)
            closing = (
                aclosing(raw_stream)
                if callable(getattr(raw_stream, "aclose", None))
                else nullcontext(raw_stream)
            )
            async with closing as stream:
                async for chunk in stream:
                    try:
                        now = time.perf_counter()
                        chunk_count += 1
                        gap_ms = (now - last_chunk_at) * 1000
                        if chunk_count > 1:
                            max_gap_ms = max(max_gap_ms, gap_ms)
                        last_chunk_at = now
                        if first_output_ms is None:
                            first_output_ms = (now - started) * 1000
                            self._record("formal_model_first_output", seq, origin_context=timing_ids, elapsed_ms=first_output_ms)
                        elif gap_ms >= 1000:
                            self._record("formal_model_stream_gap", seq, origin_context=timing_ids, elapsed_ms=(now - started) * 1000,
                                         max_chunk_gap_ms=gap_ms, chunk_count=chunk_count)
                        content = _get(chunk, "content")
                        if isinstance(content, str):
                            chars += len(content)
                            if chars <= _MAX_TEXT:
                                digest.update(content.encode())
                            else:
                                known = False
                        elif content is not None:
                            known = False
                    except Exception:
                        known = False
                    yield chunk
        except BaseException as error:
            profile_snapshot_event("model_stream_settled", timing_ids, model_call_id=model_call_id, model_call_seq=seq,
                          outcome="cancelled" if isinstance(error, (asyncio.CancelledError, GeneratorExit)) else "failed",
                          duration_ms=(time.perf_counter() - started) * 1000, **error_fields(error),
                          first_output_ms=first_output_ms, chunk_count=chunk_count, max_chunk_gap_ms=max_gap_ms)
            self._record(
                "formal_model_result",
                seq,
                origin_context=timing_ids,
                outcome="cancelled"
                if isinstance(error, (asyncio.CancelledError, GeneratorExit))
                else "failed",
                elapsed_ms=(time.perf_counter() - started) * 1000,
                first_output_ms=first_output_ms, chunk_count=chunk_count,
                max_chunk_gap_ms=max_gap_ms,
            )
            raise
        profile_snapshot_event("model_stream_settled", timing_ids, model_call_id=model_call_id, model_call_seq=seq, outcome="complete",
                      duration_ms=(time.perf_counter() - started) * 1000,
                      first_output_ms=first_output_ms, chunk_count=chunk_count, max_chunk_gap_ms=max_gap_ms)
        self._record(
            "formal_model_result",
            seq,
            origin_context=timing_ids,
            outcome="complete",
            elapsed_ms=(time.perf_counter() - started) * 1000,
            first_output_ms=first_output_ms, chunk_count=chunk_count,
            max_chunk_gap_ms=max_gap_ms,
            output_chars=chars,
            repeats_selected_assistant=digest.digest() in self._previous_answers
            if known
            else None,
        )


def observe_formal_model(model, *, envelope, request_id, session_id):
    """Only call for a newly created, execution-private model, never a cached one."""
    try:
        client = getattr(model, "_client", None)
        if client is not None:
            model._client = FormalModelDiagnostics(
                client, envelope=envelope, request_id=request_id, session_id=session_id
            )
    except Exception:
        pass


class TaskModelTiming:
    """Count/timing only, for a dedicated background adapter's private client."""

    def __init__(self, client, request_id, session_id):
        self._client = client
        self._ids = {"request_id": request_id, "execution_session_id": session_id}

    def __getattr__(self, name):
        return getattr(self._client, name)

    async def invoke(self, *args, **kwargs):
        with ProfileSpan("model.task_invoke", **self._ids):
            return await self._client.invoke(*args, **kwargs)

    async def stream(self, *args, **kwargs):
        # Do not enter a ContextVar span across yield: consumers may close an
        # async generator in another task. The local object owns timing only.
        started = time.perf_counter()
        timing_ids = {**current_profile_fields(), **self._ids}
        call_id = uuid.uuid4().hex
        count = 0
        first = None
        last = started
        gap = 0.0
        outcome = "complete"
        error_metadata = {}
        profile_snapshot_event("model_stream_started", timing_ids, model_call_id=call_id, outcome="started")
        try:
            raw = self._client.stream(*args, **kwargs)
            closing = aclosing(raw) if callable(getattr(raw, "aclose", None)) else nullcontext(raw)
            async with closing as stream:
                async for chunk in stream:
                    now = time.perf_counter()
                    count += 1
                    if count > 1:
                        gap = max(gap, (now - last) * 1000)
                    last = now
                    if first is None:
                        first = (now - started) * 1000
                        profile_snapshot_event("task_model_first_chunk", timing_ids, model_call_id=call_id, first_output_ms=first)
                    yield chunk
        except BaseException as error:
            outcome = "cancelled" if isinstance(error, (asyncio.CancelledError, GeneratorExit)) else "failed"
            error_metadata = error_fields(error)
            raise
        finally:
            profile_snapshot_event("model_stream_settled", timing_ids, model_call_id=call_id, outcome=outcome,
                          duration_ms=(time.perf_counter() - started) * 1000, first_output_ms=first,
                          chunk_count=count, max_chunk_gap_ms=gap, **error_metadata)


def observe_private_task_model(model, *, request_id, session_id):
    """Only the fresh dedicated background child calls this, never ordinary chat."""
    try:
        if not current_profile_fields().get("task_id"):
            return
        client = getattr(model, "_client", None)
        if isinstance(client, TaskModelTiming):
            if client._ids == {"request_id": request_id, "execution_session_id": session_id}:
                return
            client = client._client
        if client is not None:
            model._client = TaskModelTiming(client, request_id, session_id)
    except Exception:
        pass
