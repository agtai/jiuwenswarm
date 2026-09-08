"""Bounded passive wait/holder observations for existing asyncio locks."""
from __future__ import annotations

import asyncio
import sys
import time
from itertools import count

from .live_voice_audio_diagnostics import record_audio_diagnostic

_SPANS = count(1)


class ObservedAsyncLock(asyncio.Lock):
    """Preserve asyncio.Lock semantics; diagnose only waits/holds >= 20 ms.

    The parent span is the holder observed when waiting began, not a claim that
    it was the only holder while this waiter was queued. No task names, locals,
    payloads or stack dumps are recorded.
    """

    def __init__(self, name: str):
        super().__init__()
        self._diagnostic_name = name
        self._holder = "none"
        self._span = "none"
        self._held_at = 0.0

    async def __aenter__(self):
        caller = sys._getframe(1).f_code.co_name
        return await self._acquire_observed(caller)

    async def acquire(self):
        return await self._acquire_observed(sys._getframe(1).f_code.co_name)

    async def _acquire_observed(self, caller):
        started = time.perf_counter()
        parent_span, holder = self._span, self._holder
        acquired = await super().acquire()
        now = time.perf_counter()
        self._span = f"lock-{next(_SPANS)}"
        self._held_at = now
        self._holder = caller
        wait_ms = (now - started) * 1000
        if wait_ms >= 20:
            self._observe("wait", lock_wait_ms=wait_ms, parent_span_id=parent_span,
                          lock_owner=holder, lock_waiter=caller)
        return acquired

    def release(self):
        hold_ms = (time.perf_counter() - self._held_at) * 1000
        super().release()
        if hold_ms >= 20:
            self._observe("hold", lock_hold_ms=hold_ms, lock_owner=self._holder)
        self._holder, self._span = "none", "none"

    def _observe(self, stage, **fields):
        try:
            record_audio_diagnostic("registry_lock", stage=stage,
                lock_name=self._diagnostic_name, span_id=self._span, **fields)
        except Exception:
            pass
