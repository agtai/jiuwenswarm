# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Host lifetime for the existing Work journal, scheduler and Agent producers."""

from __future__ import annotations
from jiuwenswarm.common.live_voice_profiling import profile_event

import asyncio
import logging
from pathlib import Path
from typing import Any

from jiuwenswarm.server.runtime.work.native_work_journal import SqliteNativeWorkJournal
from openjiuwen.core.application.tasks.work_runtime import (
    WorkRuntime as NativeWorkRuntime,
)

logger = logging.getLogger(__name__)


class HostWorkService:
    """Borrowed by channels; only AgentRuntime closes this service."""

    def __init__(self, database_path: str | Path, *, agent_manager: Any) -> None:
        self.journal = SqliteNativeWorkJournal(database_path)
        self.work_runtime = NativeWorkRuntime(
            save=self.journal.save,
            restored=self.journal.restore(),
            observer=profile_event,
        )
        self.executors: dict[Any, tuple[Any, Any]] = {}
        self.executor_lock = asyncio.Lock()
        self._agent_manager = agent_manager
        self.closed = False
        self.closing = False

    async def _close_executor_locked(self, key: Any) -> None:
        """Release one producer only after its real cleanup, under executor_lock."""
        from jiuwenswarm.runtime.service import RuntimeStateError

        executor, facade = self.executors[key]
        result = await executor.close(timeout_seconds=1.0)
        if not (getattr(result, "closed", False) or executor.snapshot().closed):
            raise RuntimeStateError("work producer cleanup is incomplete")
        unpin = getattr(self._agent_manager, "unpin_agent", None)
        if callable(unpin):
            unpin(facade)
        del self.executors[key]

    async def retire_previous_generations_locked(
        self, scope: Any, generation: int
    ) -> None:
        """Reclaim idle predecessors while the caller holds executor_lock.

        Unknown or active physical work keeps its slot and Agent pin. A failed
        retirement is retained for another attempt or final Host shutdown.
        """
        if any(
            not item.execution_settled for item in self.work_runtime.list(scope=scope)
        ):
            return
        for key, (executor, _facade) in tuple(self.executors.items()):
            binding = (
                key[1]
                if isinstance(key, tuple) and len(key) == 3 and key[0] == "cleanup"
                else key
            )
            if not (
                isinstance(binding, tuple)
                and len(binding) == 2
                and binding[0] == scope
                and binding[1] != generation
            ):
                continue
            try:
                snapshot = executor.snapshot()
                if not snapshot.closed and not (
                    getattr(snapshot, "active_requests", None) == ()
                    and getattr(
                        getattr(snapshot, "harness", None), "active_rounds", None
                    )
                    == ()
                ):
                    continue
                await self._close_executor_locked(key)
            except Exception as error:
                logger.warning(
                    "Work predecessor cleanup remains pending: %s", type(error).__name__
                )

    async def close(self) -> None:
        if self.closed:
            return
        # Fence allocation before waiting for an in-flight startup. Its cleanup
        # record must be published under the same lock before we take a snapshot.
        self.closing = True
        async with self.executor_lock:
            if self.closed:
                return
            errors: list[BaseException] = []
            try:
                await self.work_runtime.close()
            except BaseException as error:
                errors.append(error)
            for key in tuple(self.executors):
                try:
                    await self._close_executor_locked(key)
                except BaseException as error:
                    errors.append(error)
            try:
                settled = await self.work_runtime.close()
                if any(not item.execution_settled for item in settled):
                    from jiuwenswarm.runtime.service import RuntimeStateError

                    errors.append(
                        RuntimeStateError("work execution settlement is incomplete")
                    )
            except BaseException as error:
                errors.append(error)
            if errors:
                raise errors[0]
            self.closed = True
