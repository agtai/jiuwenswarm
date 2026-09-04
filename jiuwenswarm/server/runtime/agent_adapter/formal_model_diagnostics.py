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
from contextlib import aclosing, nullcontext

from jiuwenswarm.common.live_voice_audio_diagnostics import record_audio_diagnostic

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
        self._ids = {"request_id": request_id, "session_id": session_id}
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

    def _record(self, event, seq, **fields):
        try:
            if seq <= _MAX_CALLS:
                record_audio_diagnostic(
                    event, **self._ids, model_call_seq=seq, **fields
                )
        except Exception:
            pass

    def _begin(self, args, kwargs):
        self._sequence += 1
        seq = self._sequence
        started = time.monotonic()
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
            result = await self._client.invoke(*args, **kwargs)
        except BaseException as error:
            self._record(
                "formal_model_result",
                seq,
                outcome="cancelled"
                if isinstance(error, asyncio.CancelledError)
                else "failed",
                elapsed_ms=(time.monotonic() - started) * 1000,
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
                elapsed_ms=(time.monotonic() - started) * 1000,
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
        digest = hashlib.sha256()
        chars = 0
        known = True
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
            self._record(
                "formal_model_result",
                seq,
                outcome="cancelled"
                if isinstance(error, (asyncio.CancelledError, GeneratorExit))
                else "failed",
                elapsed_ms=(time.monotonic() - started) * 1000,
            )
            raise
        self._record(
            "formal_model_result",
            seq,
            outcome="complete",
            elapsed_ms=(time.monotonic() - started) * 1000,
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
