# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Host lifetime for the existing Work journal, scheduler and Agent producers."""

from __future__ import annotations
from jiuwenswarm.common.live_voice_profiling import profile_event

import asyncio
import logging
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jiuwenswarm.server.runtime.work.native_work_journal import SqliteNativeWorkJournal
from openjiuwen.core.application.tasks.work_runtime import (
    WorkRuntime as NativeWorkRuntime,
)

logger = logging.getLogger(__name__)


class HostWorkAgentExecutor:
    """Adapt durable Work to the existing Host round owner; no second scheduler."""

    def __init__(self, *, scope, instance_id, facade, max_concurrency=4, max_requests=128):
        from jiuwenswarm.server.runtime.agent_adapter.jiuwenswarm_round_harness import JiuWenSwarmRoundHarness

        self._scope = scope
        self._facade = facade
        self._harness = JiuWenSwarmRoundHarness(
            instance_id=instance_id, max_active_rounds=max_concurrency,
            max_reservations=max_requests,
        )

    async def start(self):
        return self._facade.supports_formal_live_voice()

    def snapshot(self):
        return self._harness.snapshot()

    async def close(self, *, timeout_seconds):
        try:
            await asyncio.wait_for(self._harness.close(), timeout_seconds)
        except TimeoutError:
            pass  # Harness retains its close coordinator for the next retry.
        return self.snapshot()

    async def execute_work(self, *, control, commit, context, instruction, correlation_id, channel_id="web"):
        from openjiuwen.core.application.tasks.work_runtime import WorkControl, WorkCancelled, WorkViolation, context_identity
        from jiuwenswarm.common.schema.live_voice_contract_v2 import CommandEnvelope, ErrorCode, ResponseRef, TurnCommit
        from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import FormalContextSnapshot
        from jiuwenswarm.server.runtime.agent_adapter.jiuwenswarm_round_harness import HarnessRoundBinding

        if (not isinstance(control, WorkControl) or not isinstance(commit, TurnCommit)
                or not isinstance(context, FormalContextSnapshot)
                or control.snapshot.scope != self._scope or commit.scope != self._scope
                or control.snapshot.input_id != commit.commit_id
                or control.snapshot.context_id != context_identity(context)
                or control.snapshot.instruction != instruction):
            raise WorkViolation("NATIVE_WORK_BINDING_MISMATCH", "Work requires its exact admitted input and context", ErrorCode.PERMISSION_DENIED)
        context.validate_for(commit)
        control.check()
        identity = control.snapshot
        request_id = f"{identity.work_id}:r{identity.revision}"
        reservation = self._harness.reserve_round(
            HarnessRoundBinding(request_id, request_id, correlation_id, commit), facade=self._facade,
        )
        try:
            handle = self._harness.commit_round(
                reservation, response_ref=ResponseRef(commit.interaction_id, request_id, 1),
                context=context, facade=self._facade, channel_id=channel_id,
                allow_tools=True, read_only_tools=True,
                model_identity=identity.model_identity, model_config_version=identity.model_config_version,
            )
        except BaseException:
            self._harness.rollback_unstarted_round(reservation, reason="work_admission_failed")
            raise
        completion = asyncio.create_task(handle.collect_final_text())
        # Result validity and physical cleanup are different facts: cancellation
        # has no successful final, but its runner can still settle successfully.
        control.settlement = asyncio.create_task(handle.wait_settled())
        completion.add_done_callback(lambda task: None if task.cancelled() else task.exception())
        control.observe("agent_started")
        try:
            result = await control.read_only(asyncio.shield(completion))
            control.check()
            control.observe("agent_completed", outcome="complete")
            return result
        except WorkCancelled as error:
            handle.cancel(CommandEnvelope.from_dict({
                "contract_version": "live-voice.contract.v2", "request_id": request_id,
                "command_id": "work-cancel-" + hashlib.sha256(request_id.encode()).hexdigest(),
                "command_type": "round.cancel",
                "issued_at": datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
                "scope": commit.scope.to_dict(), "correlation_id": correlation_id, "causation_id": None,
                "origin": {"kind": "committed_turn", "turn_id": commit.turn_id, "commit_id": commit.commit_id},
                "target_ref": {"kind": "round", "id": handle.round_id},
                "context_refs": [], "required_capabilities": ["round.cancel"], "payload": {}, "extensions": {},
            }))
            try:
                terminal = await asyncio.wait_for(asyncio.shield(control.settlement), 1.0)
            except TimeoutError:
                raise WorkViolation("NATIVE_WORK_CANCEL_OUTCOME_UNKNOWN", "Work cleanup remains pending", ErrorCode.RESULT_UNKNOWN) from error
            if terminal is None or terminal.payload.get("outcome") not in {"cancelled", "completed"}:
                raise WorkViolation("NATIVE_WORK_CANCEL_OUTCOME_UNKNOWN", "Work cancellation did not confirm successful cleanup", ErrorCode.RESULT_UNKNOWN) from error
            raise WorkViolation("NATIVE_WORK_CANCELLED", "Work cancellation settled", ErrorCode.CANCELLED) from error


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
                if not snapshot.closed and getattr(snapshot, "active_rounds", None) != ():
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
