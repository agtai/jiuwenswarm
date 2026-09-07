# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Wait for a caller-owned operation without merging cancellation authorities."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def cancellable_read(
    operation: Awaitable[T],
    *,
    stopped: asyncio.Event,
    check: Callable[[], None],
    timeout: float | None = None,
) -> T:
    """The caller must own cancellation; never wrap a durable Task dispatch."""
    work = asyncio.ensure_future(operation)
    stop = asyncio.create_task(stopped.wait())
    try:
        done, _ = await asyncio.wait(
            {work, stop}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
        check()
        if work not in done:
            raise TimeoutError
        return await work
    finally:
        for task in (work, stop):
            if not task.done():
                task.cancel()
        await asyncio.gather(work, stop, return_exceptions=True)
