"""The host store: one SQLite file, used from a single worker thread.

The standard ``sqlite3`` module runs behind a one-thread executor instead of
aiosqlite: aiosqlite keeps a non-daemon thread per connection, and since the
Gateway never calls a plugin's ``shutdown()``, an open connection would keep the
process from exiting. Idle executor threads do not.

Repositories are plain synchronous functions that take the connection; a caller
runs a whole unit of work with ``await store.transact(fn)``.
"""

from __future__ import annotations

import asyncio
import functools
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, TypeVar

from jiuwenswarm.extensions.blackboard.common.clock import now_iso
from jiuwenswarm.extensions.blackboard.host.store.migrations import migrate

T = TypeVar("T")


__all__ = ["Store", "now_iso"]


class Store:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._executor: ThreadPoolExecutor | None = None
        self._conn: sqlite3.Connection | None = None

    @property
    def is_open(self) -> bool:
        return self._conn is not None

    async def open(self) -> int:
        """Open the file and apply migrations. Returns the schema version."""
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="blackboard-store")
        return await self._run(self._open_sync)

    def _open_sync(self) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None: autocommit, transactions are explicit BEGIN/COMMIT.
        conn = sqlite3.connect(self.path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        version = migrate(conn)
        self._conn = conn
        return version

    async def transact(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        """Run ``fn(conn)`` in one write transaction; roll back if it raises."""
        return await self._run(self._transact_sync, fn)

    def _transact_sync(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        conn = self._require_conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            result = fn(conn)
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
        return result

    async def read(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        """Run ``fn(conn)`` without a write lock."""
        return await self._run(lambda: fn(self._require_conn()))

    async def close(self) -> None:
        if self._executor is None:
            return
        await self._run(self._close_sync)
        self._executor.shutdown(wait=True)
        self._executor = None

    def _close_sync(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("store is not open")
        return self._conn

    async def _run(self, fn: Callable[..., T], *args: Any) -> T:
        if self._executor is None:
            raise RuntimeError("store is not open")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, functools.partial(fn, *args))
