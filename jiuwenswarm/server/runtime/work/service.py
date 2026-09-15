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

    def __init__(self, database_path: str | Path, *, runtime: Any) -> None:
        self.journal = SqliteNativeWorkJournal(database_path)
        self.work_runtime = NativeWorkRuntime(
            save=self.journal.save,
            restored=self.journal.restore(),
            observer=profile_event,
            task_group_provider=runtime.get_background_task_group,
        )
        self._executors: dict[Any, tuple[Any, Any]] = {}
        self._executor_lock = asyncio.Lock()
        self._runtime = runtime
        self._agent_manager = runtime.agent_manager
        self.closed = False
        self.closing = False

    @staticmethod
    async def require_execution_authority(*, composition, authority, scope):
        """Revalidate admitted Work through the existing Host authority owner."""
        from openjiuwen.core.application.tasks.work_runtime import WorkViolation
        from openjiuwen.core.application.tasks.contracts import ErrorCode

        if not composition._accepting:
            raise WorkViolation("NATIVE_WORK_AUTHORITY_UNAVAILABLE", "NATIVE_WORK_AUTHORITY_UNAVAILABLE",
                                code=ErrorCode.UNAVAILABLE)
        now = composition._clock()
        current = await asyncio.to_thread(
            composition._resolve_native_activation_authority, authority,
            operation="agent.chat", session_id=scope.session_id, now=now, require_clean=False,
        )
        current.context.require_usable(scope=scope,
            required_permissions=frozenset({"task.execute", "project.write"}), destructive=False, now=now)
        if current.context.file_path != authority.context.file_path:
            raise WorkViolation("EXECUTION_CONTEXT_SCOPE_MISMATCH", "EXECUTION_CONTEXT_SCOPE_MISMATCH",
                                code=ErrorCode.PERMISSION_DENIED)

    async def submit(
        self, *, operation, scope, request_id, commit, context, instruction,
        authority, composition, correlation_id, work_id=None, revision=None, channel_id="web",
    ):
        """Admit and own a Work producer without retaining its channel route."""
        from openjiuwen.core.application.tasks.work_runtime import WorkViolation, context_identity
        from openjiuwen.core.application.tasks.contracts import ErrorCode

        if operation not in {"work.start", "work.update"}:
            raise WorkViolation("NATIVE_BUSINESS_OPERATION_UNSUPPORTED", "Work submission requires start or update")
        if commit.scope != scope or context.scope != scope:
            raise WorkViolation("NATIVE_WORK_BINDING_MISMATCH", "Work requires its exact committed scope",
                                code=ErrorCode.PERMISSION_DENIED)
        context.validate_for(commit)
        executor = await self.get_executor(scope=scope, project_dir=authority.context.file_path)
        await self.require_execution_authority(composition=composition, authority=authority, scope=scope)

        async def run(control):
            control.check()
            await self.require_execution_authority(composition=composition, authority=authority, scope=scope)
            control.check()
            return await executor.execute_work(
                control=control, commit=commit, context=context, instruction=instruction,
                correlation_id=correlation_id, channel_id=channel_id,
            )

        arguments = dict(
            scope=scope, request_id=request_id, input_id=commit.commit_id, instruction=instruction,
            model_identity=authority.model_identity, model_config_version=authority.model_config_version,
            context_id=context_identity(context), runner=run,
        )
        if operation == "work.start":
            return await self.work_runtime.start(**arguments, foreground=True)
        return await self.work_runtime.update(**arguments, work_id=work_id, revision=revision)

    async def get_executor(self, *, scope, project_dir):
        """Borrow the Host-owned producer for this existing session generation."""
        from openjiuwen.core.application.tasks.work_runtime import WorkViolation
        from openjiuwen.core.application.tasks.contracts import ErrorCode, canonical_json_bytes

        def current_key():
            from jiuwenswarm.runtime.session import RuntimeSessionState
            if self.closing or self.closed:
                raise WorkViolation("NATIVE_WORK_HOST_UNAVAILABLE", "NATIVE_WORK_HOST_UNAVAILABLE", code=ErrorCode.UNAVAILABLE)
            snapshot = self._runtime.session_coordinator.snapshot_session(scope.session_id)
            if snapshot is None or snapshot.state in {
                RuntimeSessionState.CLOSED, RuntimeSessionState.QUIESCING,
            }:
                raise WorkViolation("NATIVE_WORK_SESSION_UNAVAILABLE", "NATIVE_WORK_SESSION_UNAVAILABLE", code=ErrorCode.UNAVAILABLE)
            return scope, snapshot.generation

        async with self._executor_lock:
            key = current_key()
            retained = self._executors.get(key)
            if retained is not None:
                return retained[0]
            await self.retire_previous_generations_locked(scope, key[1])
            if current_key() != key:
                raise WorkViolation("NATIVE_WORK_SESSION_GENERATION_CHANGED", "NATIVE_WORK_SESSION_GENERATION_CHANGED", code=ErrorCode.STALE)
            if len(self._executors) >= 32:
                raise WorkViolation("NATIVE_WORK_SCOPE_CAPACITY", "NATIVE_WORK_SCOPE_CAPACITY", code=ErrorCode.UNAVAILABLE)
            facade = await self._agent_manager.get_agent(
                "live_voice_native_work", "agent", project_dir, None)
            if current_key() != key:
                raise WorkViolation("NATIVE_WORK_SESSION_GENERATION_CHANGED", "NATIVE_WORK_SESSION_GENERATION_CHANGED", code=ErrorCode.STALE)
            if facade is None or not callable(getattr(facade, "process_formal_live_voice_stream", None)):
                raise WorkViolation("FORMAL_AGENT_FACADE_UNAVAILABLE", "FORMAL_AGENT_FACADE_UNAVAILABLE", code=ErrorCode.UNAVAILABLE)
            pin = getattr(self._agent_manager, "pin_agent", None)
            if callable(pin):
                pin(facade)
            identity_source = {
                "scope": scope.to_dict(), "session_generation": key[1],
            }
            identity = hashlib.sha256(canonical_json_bytes(identity_source)).hexdigest()
            from jiuwenswarm.server.runtime.agent_adapter.runtime_formal import RuntimeFormalAgentFacade
            producer = RuntimeFormalAgentFacade(
                runtime=self._runtime, agent=facade, scope=scope,
                agent_channel_id="live_voice_native_work", mode="agent",
                project_dir=project_dir,
            )
            runtime = HostWorkAgentExecutor(scope=scope, instance_id="native-work-service:" + identity,
                facade=producer, max_concurrency=4, max_requests=128)
            try:
                if not await runtime.start():
                    raise WorkViolation("NATIVE_WORK_EXECUTOR_UNAVAILABLE", "NATIVE_WORK_EXECUTOR_UNAVAILABLE", code=ErrorCode.UNAVAILABLE)
                if current_key() != key:
                    raise WorkViolation("NATIVE_WORK_SESSION_GENERATION_CHANGED", "NATIVE_WORK_SESSION_GENERATION_CHANGED", code=ErrorCode.STALE)
            except BaseException:
                settled = False
                try:
                    result = await runtime.close(timeout_seconds=1.0)
                    settled = getattr(result, "closed", False) or runtime.snapshot().closed
                except BaseException:
                    pass  # Retain cleanup ownership while preserving the primary failure.
                if settled:
                    unpin = getattr(self._agent_manager, "unpin_agent", None)
                    if callable(unpin):
                        unpin(facade)
                else:
                    self._executors[("cleanup", key, id(runtime))] = (runtime, facade)
                raise
            self._executors[key] = (runtime, facade)
            return runtime

    async def _close_executor_locked(self, key: Any) -> None:
        """Release one producer only after its real cleanup, under executor_lock."""
        from jiuwenswarm.runtime.service import RuntimeStateError

        executor, facade = self._executors[key]
        result = await executor.close(timeout_seconds=1.0)
        if not (getattr(result, "closed", False) or executor.snapshot().closed):
            raise RuntimeStateError("work producer cleanup is incomplete")
        unpin = getattr(self._agent_manager, "unpin_agent", None)
        if callable(unpin):
            unpin(facade)
        del self._executors[key]

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
        for key, (executor, _facade) in tuple(self._executors.items()):
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
        async with self._executor_lock:
            if self.closed:
                return
            errors: list[BaseException] = []
            try:
                await self.work_runtime.close()
            except BaseException as error:
                errors.append(error)
            for key in tuple(self._executors):
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
