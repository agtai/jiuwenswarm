# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Historical scheduler adapter retained solely for compatibility regression tests."""
from __future__ import annotations

from jiuwenswarm.server.runtime.formal_tasks.project_code_executor import (
    Any,
    ErrorCode,
    ExecutorDeliveryResult,
    ExecutorObservation,
    ExecutorResolution,
    FORMAL_PROJECT_EXECUTOR_ID,
    FormalAttemptState,
    FormalTaskViolation,
    Mapping,
    OutboxKind,
    PROJECT_CODE_PIPELINE,
    PersistentAttemptRecord,
    PersistentOutboxItem,
    PersistentTaskRecord,
    ProjectExecutionBinding,
    ProjectExecutionBindingResolver,
    TaskAdjustmentDeliveryResult,
    TaskAdjustmentSettlement,
    TaskAdjustmentState,
    TerminalOutcome,
    _EXECUTION_TARGET_FIELDS,
    _ReleaseOnce,
    _expected_contract,
    _path_key,
    _text,
    utc_now,
)


class ProjectCodeExecutorAdapter:
    """Translate exact formal attempt IDs to legacy project-bound executions."""

    executor_id = FORMAL_PROJECT_EXECUTOR_ID

    def __init__(self, resolver: ProjectExecutionBindingResolver) -> None:
        self._resolver = resolver

    async def dispatch(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
        self._require_item(item)
        binding = await self._resolver.resolve(item.spec, for_dispatch=True)
        release = (
            _ReleaseOnce(binding.context_release)
            if binding.context_release is not None
            else None
        )
        carrier_owns_release = False
        try:
            binding.validate(item.spec, for_dispatch=True)
            if binding.execution_agent is None or not callable(
                getattr(
                    binding.project_executor,
                    "process_background_code_task_stream",
                    None,
                )
            ):
                raise FormalTaskViolation(
                    "EXECUTOR_CAPABILITY_UNAVAILABLE",
                    "legacy project dispatch requires the root execution Agent",
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                )
            if binding.service is None:
                raise FormalTaskViolation(
                    "LEGACY_EXECUTOR_UNAVAILABLE",
                    "legacy schedule carrier is unavailable",
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                )
            assert binding.dispatch_fence is not None
            await binding.dispatch_fence()
            payload = await binding.service.run_task(
                item.spec.instruction,
                binding.model,
                PROJECT_CODE_PIPELINE,
                execution_agent=binding.execution_agent,
                project_executor=binding.project_executor,
                effective_execution_root=binding.effective_execution_root,
                context_release=release,
                execution_target=dict(binding.execution_target),
                owner_scope=dict(binding.owner_scope),
                origin_namespace="live_voice",
                idempotency_key=item.attempt_id,
                model_intent=binding.model_identity,
            )
            task_id = _text(payload, "task_id")
            if task_id is None:
                raise self._delivery_error(payload)
            carrier_owns_release = True
        finally:
            if not carrier_owns_release and release is not None:
                release()
        try:
            self._validate_carrier_projection(
                payload,
                binding,
                task_id,
                item.attempt_id,
                require_provenance=False,
            )
            persisted = await binding.service.get_scheduled_task_status(
                task_id,
                requester_owner_scope=dict(binding.owner_scope),
                requester_execution_target=dict(binding.execution_target),
            )
            self._validate_carrier_projection(
                persisted,
                binding,
                task_id,
                item.attempt_id,
                require_provenance=True,
            )
            dispatch_result = self._known_result(
                item=item,
                executor_ref=task_id,
                payload=payload,
            )
            persisted_result = self._known_result(
                item=item,
                executor_ref=task_id,
                payload=persisted,
            )
            return max(
                (persisted_result, dispatch_result),
                key=lambda result: len(result.observations),
            )
        except FormalTaskViolation as error:
            raise self._result_unknown(error) from error

    async def cancel(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
        self._require_item(item)
        if item.executor_ref is None:
            raise FormalTaskViolation(
                "EXECUTOR_REFERENCE_REQUIRED",
                "formal cancellation requires the bound original executor reference",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        binding = await self._resolver.resolve(item.spec, for_dispatch=False)
        release = (
            _ReleaseOnce(binding.context_release)
            if binding.context_release is not None
            else None
        )
        try:
            return await self._cancel_bound(item, binding)
        finally:
            if release is not None:
                release()

    async def adjust(self, item: PersistentOutboxItem) -> TaskAdjustmentDeliveryResult:
        if (
            item.kind is not OutboxKind.ATTEMPT_ADJUST
            or item.adjustment is None
            or item.executor_ref is None
        ):
            raise FormalTaskViolation(
                "EXECUTOR_OPERATION_MISMATCH",
                "legacy adjustment delivery is not canonical",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        return TaskAdjustmentDeliveryResult(
            item.executor_ref,
            item.command_id,
            TaskAdjustmentState.REJECTED,
            "ADJUSTMENT_CHECKPOINT_UNAVAILABLE",
        )

    async def settle_adjustment(
        self,
        item: PersistentOutboxItem,
        settlement: TaskAdjustmentSettlement,
    ) -> None:
        return None

    async def _cancel_bound(
        self,
        item: PersistentOutboxItem,
        binding: ProjectExecutionBinding,
    ) -> ExecutorDeliveryResult:
        assert item.executor_ref is not None
        binding.validate(item.spec, for_dispatch=False)
        if binding.service is None:
            raise FormalTaskViolation(
                "LEGACY_EXECUTOR_UNAVAILABLE",
                "legacy schedule carrier is unavailable",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        payload = await binding.service.cancel_scheduled_task(
            item.executor_ref,
            requester_owner_scope=dict(binding.owner_scope),
            requester_execution_target=dict(binding.execution_target),
        )
        if payload.get("error") is not None:
            payload = await binding.service.get_scheduled_task_status(
                item.executor_ref,
                requester_owner_scope=dict(binding.owner_scope),
                requester_execution_target=dict(binding.execution_target),
            )
        try:
            self._validate_carrier_projection(
                payload,
                binding,
                item.executor_ref,
                item.attempt_id,
                require_provenance=True,
            )
            return self._known_result(
                item=item,
                executor_ref=item.executor_ref,
                payload=payload,
            )
        except FormalTaskViolation as error:
            raise self._result_unknown(error) from error

    async def status(
        self,
        task: PersistentTaskRecord,
        attempt: PersistentAttemptRecord,
    ) -> ExecutorDeliveryResult | ExecutorObservation:
        if (
            attempt.executor_id != self.executor_id
            or task.attempt_id != attempt.attempt_id
        ):
            raise FormalTaskViolation(
                "EXECUTOR_BINDING_MISMATCH",
                "reconciliation must query the exact original formal attempt",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if attempt.executor_ref is None:
            return self._resolution_observation(
                task.task_id,
                attempt.attempt_id,
                None,
                ExecutorResolution.UNAVAILABLE,
                "EXECUTOR_REFERENCE_NOT_BOUND",
            )
        binding = await self._resolver.resolve(task.spec, for_dispatch=False)
        release = (
            _ReleaseOnce(binding.context_release)
            if binding.context_release is not None
            else None
        )
        try:
            return await self._status_bound(task, attempt, binding)
        finally:
            if release is not None:
                release()

    async def _status_bound(
        self,
        task: PersistentTaskRecord,
        attempt: PersistentAttemptRecord,
        binding: ProjectExecutionBinding,
    ) -> ExecutorDeliveryResult | ExecutorObservation:
        assert attempt.executor_ref is not None
        binding.validate(task.spec, for_dispatch=False)
        if binding.service is None:
            raise FormalTaskViolation(
                "LEGACY_EXECUTOR_UNAVAILABLE",
                "legacy schedule carrier is unavailable",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        payload = await binding.service.get_scheduled_task_status(
            attempt.executor_ref,
            requester_owner_scope=dict(binding.owner_scope),
            requester_execution_target=dict(binding.execution_target),
        )
        code = _text(payload, "code")
        if _text(payload, "task_id") != attempt.executor_ref:
            raise FormalTaskViolation(
                "LEGACY_EXECUTOR_REFERENCE_MISMATCH",
                "legacy status response does not identify the original attempt",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if code == "TASK_NOT_FOUND":
            return self._resolution_observation(
                task.task_id,
                attempt.attempt_id,
                attempt.executor_ref,
                ExecutorResolution.LOST,
                code,
            )
        if payload.get("error") is not None:
            if code in {"TASK_SCOPE_MISMATCH", "TASK_PROJECT_MISMATCH"}:
                raise FormalTaskViolation(
                    "LEGACY_EXECUTOR_ACCESS_MISMATCH",
                    "trusted ED binding no longer matches the original legacy attempt",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            return self._resolution_observation(
                task.task_id,
                attempt.attempt_id,
                attempt.executor_ref,
                ExecutorResolution.UNAVAILABLE,
                code or "LEGACY_EXECUTOR_STATUS_UNAVAILABLE",
            )
        self._validate_carrier_projection(
            payload,
            binding,
            attempt.executor_ref,
            attempt.attempt_id,
            require_provenance=True,
        )
        return self._known_result_for_attempt(
            task.task_id,
            attempt.attempt_id,
            attempt.executor_ref,
            attempt.source_seq,
            payload,
        )

    @staticmethod
    def _result_unknown(error: FormalTaskViolation) -> FormalTaskViolation:
        return FormalTaskViolation(
            error.reason,
            f"legacy attempt exists but its result cannot be accepted: {error}",
            ErrorCode.RESULT_UNKNOWN,
        )

    def _require_item(self, item: PersistentOutboxItem) -> None:
        if item.spec.executor_id != self.executor_id:
            raise FormalTaskViolation(
                "EXECUTOR_BINDING_MISMATCH",
                "outbox item targets a different Executor",
                ErrorCode.PROTOCOL_VIOLATION,
            )

    @staticmethod
    def _delivery_error(payload: Mapping[str, Any]) -> FormalTaskViolation:
        code = _text(payload, "code")
        message = (
            _text(payload, "error", "message")
            or "legacy project Executor rejected delivery"
        )
        if code in {
            "EXECUTION_TARGET_NOT_BOUND",
            "UNSUPPORTED_PROJECT_TASK_CONSTRAINT",
            "IDEMPOTENCY_CONFLICT",
        }:
            error_code = ErrorCode.PERMISSION_DENIED
        else:
            error_code = ErrorCode.UNAVAILABLE
        return FormalTaskViolation(
            code or "EXECUTOR_DELIVERY_UNAVAILABLE", message, error_code
        )

    @staticmethod
    def _validate_carrier_projection(
        payload: Mapping[str, Any],
        binding: ProjectExecutionBinding,
        executor_ref: str,
        attempt_id: str,
        *,
        require_provenance: bool,
    ) -> None:
        if _text(payload, "task_id") != executor_ref:
            raise FormalTaskViolation(
                "LEGACY_EXECUTOR_REFERENCE_MISMATCH",
                "legacy carrier returned a different task reference",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        target = payload.get("execution_target")
        contract = payload.get("execution_contract")
        if (
            not isinstance(target, Mapping)
            or set(target) != _EXECUTION_TARGET_FIELDS
            or _path_key(str(target.get("project_dir", "")), strict=False)
            != _path_key(binding.effective_execution_root, strict=False)
        ):
            raise FormalTaskViolation(
                "EXECUTION_TARGET_MISMATCH",
                "legacy carrier did not preserve the exact project target",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if contract != _expected_contract(binding.effective_execution_root):
            raise FormalTaskViolation(
                "EXECUTION_CONTRACT_MISMATCH",
                "legacy carrier did not preserve the bounded project contract",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        assert isinstance(target, Mapping)
        if target.get("project_id") != binding.execution_target.get("project_id"):
            raise FormalTaskViolation(
                "EXECUTION_TARGET_MISMATCH",
                "legacy carrier returned a different project identity",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if any(
            target.get(field) != binding.execution_target.get(field)
            for field in ("origin_session_id", "origin_channel_id")
        ):
            raise FormalTaskViolation(
                "EXECUTION_TARGET_MISMATCH",
                "legacy carrier returned different origin target facts",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if require_provenance:
            provenance = payload.get("provenance")
            if (
                not isinstance(provenance, Mapping)
                or provenance.get("owner_scope") != dict(binding.owner_scope)
                or provenance.get("origin_namespace") != "live_voice"
                or provenance.get("idempotency_key") != attempt_id
                or provenance.get("legacy_unscoped") is not False
                or provenance.get("access") != "authorized"
            ):
                raise FormalTaskViolation(
                    "EXECUTOR_PROVENANCE_MISMATCH",
                    "legacy carrier did not preserve the formal attempt provenance",
                    ErrorCode.PROTOCOL_VIOLATION,
                )

    def _known_result(
        self,
        *,
        item: PersistentOutboxItem,
        executor_ref: str,
        payload: Mapping[str, Any],
    ) -> ExecutorDeliveryResult:
        return self._known_result_for_attempt(
            item.task_id,
            item.attempt_id,
            executor_ref,
            item.source_seq,
            payload,
        )

    def _known_result_for_attempt(
        self,
        task_id: str,
        attempt_id: str,
        executor_ref: str,
        source_seq: int,
        payload: Mapping[str, Any],
    ) -> ExecutorDeliveryResult:
        status = _text(payload, "status")
        if status is None:
            raise FormalTaskViolation(
                "EXECUTOR_STATUS_REQUIRED",
                "legacy Executor response lacks a stable status",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        target_state, outcome = self._map_status(status)
        target_seq = {
            FormalAttemptState.ACCEPTED: 0,
            FormalAttemptState.RUNNING: 1,
            FormalAttemptState.TERMINAL: 2,
        }[target_state]
        states = (
            (FormalAttemptState.ACCEPTED, None),
            (FormalAttemptState.RUNNING, None),
            (FormalAttemptState.TERMINAL, outcome),
        )
        observed_at = utc_now()
        summary = _text(payload, "message", "progress_summary")
        error = _text(payload, "last_error", "error")
        observations = []
        for seq in range(source_seq + 1, target_seq + 1):
            state, state_outcome = states[seq]
            observations.append(
                ExecutorObservation(
                    resolution=ExecutorResolution.KNOWN,
                    executor_id=self.executor_id,
                    executor_ref=executor_ref,
                    task_id=task_id,
                    attempt_id=attempt_id,
                    source_event_id=(
                        f"{executor_ref}:formal-lifecycle:{seq}:"
                        f"{state.value}:{'' if state_outcome is None else state_outcome.value}"
                    ),
                    source_seq=seq,
                    attempt_state=state,
                    attempt_outcome=state_outcome,
                    occurred_at=observed_at,
                    raw_status=status,
                    summary=summary,
                    error=error,
                )
            )
        return ExecutorDeliveryResult(executor_ref, tuple(observations))

    @staticmethod
    def _map_status(status: str) -> tuple[FormalAttemptState, TerminalOutcome | None]:
        normalized = status.strip().lower()
        if normalized == "pending":
            return FormalAttemptState.ACCEPTED, None
        if normalized == "running":
            return FormalAttemptState.RUNNING, None
        if normalized in {"success", "completed"}:
            return FormalAttemptState.TERMINAL, TerminalOutcome.COMPLETED
        if normalized == "failed":
            return FormalAttemptState.TERMINAL, TerminalOutcome.FAILED
        if normalized == "cancelled":
            return FormalAttemptState.TERMINAL, TerminalOutcome.CANCELLED
        if normalized in {"needs_human", "skipped", "interrupted"}:
            return FormalAttemptState.TERMINAL, TerminalOutcome.INTERRUPTED
        raise FormalTaskViolation(
            "UNSUPPORTED_EXECUTOR_STATUS",
            f"legacy Executor status {status!r} is not valid for project Code Agent tasks",
            ErrorCode.PROTOCOL_VIOLATION,
        )

    def _resolution_observation(
        self,
        task_id: str,
        attempt_id: str,
        executor_ref: str | None,
        resolution: ExecutorResolution,
        error: str,
    ) -> ExecutorObservation:
        return ExecutorObservation(
            resolution=resolution,
            executor_id=self.executor_id,
            executor_ref=executor_ref,
            task_id=task_id,
            attempt_id=attempt_id,
            source_event_id=None,
            source_seq=None,
            attempt_state=None,
            attempt_outcome=None,
            occurred_at=utc_now(),
            raw_status=None,
            error=error,
        )
