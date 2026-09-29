"""Calls per minute, so a looping agent or bot cannot flood the host (milestone 7).

In memory: a restart forgets the counts, which only lets a caller start its minute again.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Callable

from jiuwenswarm.extensions.blackboard.common.errors import RATE_LIMITED, BlackboardError

WINDOW_S = 60.0
# Read calls of one agent (per member token) or of one person through a bot.
READS_PER_MINUTE = 60
# Everything one bot sends, for all the people it serves.
BOT_CALLS_PER_MINUTE = 600


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str, limit: int) -> None:
        """Count a call under `key`, or refuse it when the last minute already had `limit`."""
        now = self._clock()
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= WINDOW_S:
            hits.popleft()
        if len(hits) >= limit:
            retry = max(1, int(WINDOW_S - (now - hits[0])) + 1)
            raise BlackboardError(RATE_LIMITED, f"too many calls; try again in {retry} s", {"retry_after": retry})
        hits.append(now)
