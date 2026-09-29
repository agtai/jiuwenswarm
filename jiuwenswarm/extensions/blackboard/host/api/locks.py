"""Waiting for a document lock. The doc_locks table says who holds a lock; this keeps the waiters in
order and wakes them when a mandate lets go."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

# Waiters check again at least this often, in case a wake-up came before they waited.
POLL_S = 1.0


class LockWaits:
    def __init__(self) -> None:
        self._released = asyncio.Condition()
        self._queues: dict[str, list[str]] = {}

    def waiting(self) -> int:
        """Edits waiting for a document, on every document."""
        return sum(len(queue) for queue in self._queues.values())

    def position(self, doc_id: str, mandate_id: str) -> int:
        queue = self._queues.get(doc_id, [])
        return queue.index(mandate_id) + 1 if mandate_id in queue else 0

    async def acquire(self, doc_id: str, mandate_id: str, try_lock: Callable[[], Awaitable[bool]], timeout: float) -> int | None:
        """None once `try_lock` succeeds; else the queue position when `timeout` runs out."""
        if await try_lock():
            return None
        queue = self._queues.setdefault(doc_id, [])
        queue.append(mandate_id)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        try:
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return self.position(doc_id, mandate_id)
                async with self._released:
                    try:
                        await asyncio.wait_for(self._released.wait(), min(remaining, POLL_S))
                    except asyncio.TimeoutError:
                        pass
                if queue[0] == mandate_id and await try_lock():
                    return None
        finally:
            queue.remove(mandate_id)
            if not queue:
                self._queues.pop(doc_id, None)

    async def released(self) -> None:
        async with self._released:
            self._released.notify_all()
