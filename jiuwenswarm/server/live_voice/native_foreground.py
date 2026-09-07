# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Exact Native foreground cancellation; never authority to cancel a business Task."""

from __future__ import annotations

from .cancellable_read import cancellable_read

import asyncio
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Awaitable, TypeVar

from jiuwenswarm.common.live_voice_profiling import profile_event
from jiuwenswarm.common.schema.live_voice_contract_v2 import ErrorCode, ResponseRef

T = TypeVar("T")


class NativeForegroundInterrupted(ValueError):
    reason = "NATIVE_DELEGATE_INTERRUPTED"
    code = ErrorCode.CANCELLED


@dataclass(slots=True)
class NativeForegroundControl:
    source_response: ResponseRef
    identities: dict[str, object]
    interrupted: asyncio.Event = field(default_factory=asyncio.Event)
    started: float = field(default_factory=time.monotonic)
    deadline: float | None = None
    business_task_id: str | None = None

    def interrupt(self) -> None:
        if not self.interrupted.is_set():
            self.interrupted.set()
            self.observe("interrupted", outcome="cancelled")

    def check(self) -> None:
        if self.interrupted.is_set():
            raise NativeForegroundInterrupted("Native foreground was interrupted")

    def observe(self, stage: str, **fields: object) -> None:
        budget = fields.get("timeout_ms")
        if isinstance(budget, (int, float)):
            self.deadline = time.monotonic() + budget / 1000
        fields["elapsed_ms"] = (time.monotonic() - self.started) * 1000
        if self.deadline is not None:
            fields["remaining_ms"] = max(0, self.deadline - time.monotonic()) * 1000
        profile_event("native_foreground", **self.identities, milestone=stage, **fields)

    async def run(self, operation: Awaitable[T]) -> T:
        token = NATIVE_FOREGROUND.set(self)
        try:
            return await operation
        finally:
            NATIVE_FOREGROUND.reset(token)

    async def read_only(
        self, operation: Awaitable[T], *, timeout: float | None = None
    ) -> T:
        return await cancellable_read(
            operation, stopped=self.interrupted, check=self.check, timeout=timeout
        )


NATIVE_FOREGROUND: ContextVar[NativeForegroundControl | None] = ContextVar(
    "native_foreground", default=None
)
