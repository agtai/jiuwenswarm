# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Formal persistent P3 Task Core and durable outbox orchestration."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import ClassVar, Protocol

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    CommandEnvelope,
    ContractViolation,
    ErrorCode,
    QueryEnvelope,
    ResultEnvelope,
    ScopeRef,
    WorkProgressEventV2,
)

from .formal_task_models import (
    AdmissionPolicy,
    AppliedTaskRetryReplay,
    ExecutorDeliveryResult,
    ExecutorObservation,
    ExecutorResolution,
    ExecutorRetryReadiness,
    FormalTaskSpec,
    FormalTaskViolation,
    OutboxKind,
    PersistedExecutorSelection,
    PersistentAdmissionRecord,
    PersistentAttemptRecord,
    PersistentOutboxItem,
    PersistentTaskEvent,
    PersistentTaskRecord,
    ResolvedTaskContext,
    TaskAdjustmentDeliveryResult,
    TaskAdjustmentSettlement,
    TaskAdjustmentState,
    TaskAuthorizationGrant,
    TaskCommandDisposition,
    TaskMutationDisposition,
    TaskMutationResult,
    TaskResultAvailability,
    TaskRetryAuthoritySnapshot,
    TaskRetryProductRequestFingerprint,
    canonical_task_adjustment_rejection_reason,
    command_result_extensions,
    require_exact_payload,
    utc_now,
)
from .durability_identity import DurabilityProfileBinding
from .durability_authority import DurabilityMutationAuthorization
from .durability_recovery_facts import ExecutorRecoveryFacts
from .task_store import SqliteTaskStore

_PROJECTABLE_TASK_EVENTS = frozenset(
    {
        "task.accepted",
        "task.retry_accepted",
        "task.running",
        "task.blocked",
        "task.decision_required",
        "task.terminal",
    }
)
_OUTBOX_CLAIM_LEASE = timedelta(minutes=5)


class FormalExecutor(Protocol):
    executor_id: str

    async def dispatch(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
        """Idempotently accept the exact formal attempt."""

    async def cancel(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
        """Request cancellation of the exact bound attempt."""

    async def adjust(self, item: PersistentOutboxItem) -> TaskAdjustmentDeliveryResult:
        """Durably consume one ordered adjustment at a live safe checkpoint."""

    async def settle_adjustment(
        self,
        item: PersistentOutboxItem,
        settlement: TaskAdjustmentSettlement,
    ) -> None:
        """Open the Executor terminal fence after Store-owned final truth."""

    async def status(
        self, task: PersistentTaskRecord, attempt: PersistentAttemptRecord
    ) -> ExecutorDeliveryResult | ExecutorObservation:
        """Resolve an original attempt after dispatch or process restart."""

    def retry_readiness(
        self, task: PersistentTaskRecord, attempt: PersistentAttemptRecord
    ) -> ExecutorRetryReadiness:
        """Prove exact predecessor cleanup before a bounded retry is admitted."""

    def recovery_facts(
        self,
        task: PersistentTaskRecord,
        producer_attempt: PersistentAttemptRecord,
        *,
        candidate_recovery_attempt_id: str,
        profile: DurabilityProfileBinding,
        recovery_generation: int,
        observed_at: str,
        expires_at: str,
    ) -> ExecutorRecoveryFacts:
        """Prove exact Executor/runtime/OS quiescence for linked recovery."""

    def authorize_durable_recovery(
        self,
        task: PersistentTaskRecord,
        producer_attempt: PersistentAttemptRecord,
        *,
        recovery_id: str,
        candidate_recovery_attempt_id: str,
        profile: DurabilityProfileBinding,
        recovery_generation: int,
        checkpoint_head: int,
        checkpoint_prefix_digest: str,
        effect_head: int,
        effect_prefix_digest: str,
        claim_owner_id: str,
        claim_token: str,
        claim_generation: int,
        observed_at: str,
        expires_at: str,
    ) -> tuple[ExecutorRecoveryFacts, DurabilityMutationAuthorization]:
        """Mint one Store-bound recovery receipt after Direct preflight."""


def _contract_error(error: FormalTaskViolation) -> ContractViolation:
    return ContractViolation(
        error.code,
        error.reason,
        str(error),
        retriable=error.code
        in {ErrorCode.UNAVAILABLE, ErrorCode.TIMEOUT, ErrorCode.RESULT_UNKNOWN},
    )


def _failure(
    owner: CommandEnvelope | QueryEnvelope,
    error: FormalTaskViolation,
    *,
    observed_at: str,
) -> ResultEnvelope:
    extensions: Mapping[str, object] | None = None
    contract_error = error
    if isinstance(owner, CommandEnvelope):
        if error.code in {ErrorCode.UNSUPPORTED, ErrorCode.CAPABILITY_UNAVAILABLE}:
            disposition = TaskCommandDisposition.UNSUPPORTED
        elif error.code in {ErrorCode.CONFLICT, ErrorCode.STALE}:
            disposition = TaskCommandDisposition.CONFLICT
        elif error.code is ErrorCode.TIMEOUT:
            disposition = TaskCommandDisposition.TIMEOUT
        elif error.code is ErrorCode.RESULT_UNKNOWN:
            disposition = TaskCommandDisposition.UNKNOWN
        elif error.code in {
            ErrorCode.UNAVAILABLE,
            ErrorCode.CANCELLED,
            ErrorCode.PROTOCOL_VIOLATION,
            ErrorCode.INTERNAL,
        }:
            disposition = TaskCommandDisposition.UNKNOWN
            contract_error = FormalTaskViolation(
                error.reason,
                str(error),
                ErrorCode.RESULT_UNKNOWN,
            )
        else:
            disposition = TaskCommandDisposition.REJECTED
        extensions = command_result_extensions(disposition)
    return ResultEnvelope.failure(
        owner=owner,
        error=_contract_error(contract_error).error,
        observed_at=observed_at,
        extensions=extensions,
    )


def project_task_event(event: PersistentTaskEvent) -> dict[str, object]:
    """Pure TaskEvent -> WorkProgress projection; never mutates or invokes TTS."""

    if event.event_type not in _PROJECTABLE_TASK_EVENTS:
        raise FormalTaskViolation(
            "TASK_EVENT_NOT_PROJECTABLE",
            "attempt/control/internal events cannot emit duplicate task progress",
            ErrorCode.PROTOCOL_VIOLATION,
        )
    terminal = event.state == "terminal"
    if terminal != (event.outcome is not None):
        raise FormalTaskViolation(
            "INVALID_TASK_PROGRESS_SOURCE",
            "terminal progress and outcome must agree",
            ErrorCode.PROTOCOL_VIOLATION,
        )
    details = event.details
    summary = details.get("summary")
    if summary is not None and type(summary) is not str:
        summary = None
    payload = {
        "work_ref": {"kind": "task", "id": event.task_id},
        "source": {
            "authority": "task_core",
            "event_id": event.event_id,
            "source_work_ref": {"kind": "task", "id": event.task_id},
            "adapter": (
                None if event.producer.startswith("task_core") else event.producer
            ),
        },
        "seq": event.seq,
        "state": event.state,
        "outcome": event.outcome,
        "summary": (
            {"knowledge": "unknown"}
            if summary is None
            else {"knowledge": "known", "value": summary}
        ),
        "blocking_question": {"knowledge": "unknown"},
        "artifact_refs": {"knowledge": "unknown"},
        "urgency": "unknown",
        "speakability": "not_speakable",
    }
    try:
        return WorkProgressEventV2.from_dict(payload).to_dict()
    except ContractViolation as error:
        raise FormalTaskViolation(
            "INVALID_TASK_PROGRESS_PROJECTION",
            f"Task Core produced invalid WorkProgress: {error}",
            ErrorCode.PROTOCOL_VIOLATION,
        ) from error


ReconciliationEventSink = Callable[
    [PersistentTaskEvent, PersistentAttemptRecord], Awaitable[None]
]


class PersistentTaskCore:
    """Owns formal task state; the Executor only reports attempt facts."""

    _CREATE_PAYLOAD: ClassVar[frozenset[str]] = frozenset(
        {
            "name",
            "instruction",
            "executor_id",
            "side_effect_class",
            "attributes",
        }
    )
    _SUCCESSOR_PAYLOAD: ClassVar[frozenset[str]] = frozenset(
        {
            "expected_predecessor_revision_number",
            "expected_predecessor_event_head",
            "predecessor_terminal_event_id",
            "predecessor_outcome",
            "predecessor_result_sha256",
            "name",
            "instruction",
            "constraints",
            "executor_id",
            "side_effect_class",
            "attributes",
        }
    )

    def __init__(
        self,
        store: SqliteTaskStore,
        executor: FormalExecutor,
        *,
        reconciliation_event_sink: ReconciliationEventSink | None = None,
        admission_policy: AdmissionPolicy | None = None,
    ) -> None:
        self.store = store
        self.executor = executor
        self._reconciliation_event_sink = reconciliation_event_sink
        self._admission_policy = (
            AdmissionPolicy() if admission_policy is None else admission_policy
        )
        if not isinstance(self._admission_policy, AdmissionPolicy):
            raise TypeError("admission_policy must be an AdmissionPolicy")

    def read_current_retry_authority(
        self,
        *,
        scope: ScopeRef,
        task_id: str,
    ) -> TaskRetryAuthoritySnapshot:
        """Expose Store-derived retry lineage without accepting client payload."""

        return self.store.read_current_retry_authority(scope=scope, task_id=task_id)

    async def recover_durable_attempt(
        self,
        *,
        scope: ScopeRef,
        task_id: str,
        operator_id: str,
        observed_at: str | None = None,
    ) -> PersistentAttemptRecord:
        """Operator-only, unregistered linked recovery orchestration."""

        if (
            type(operator_id) is not str
            or not operator_id.strip()
            or len(operator_id.encode("utf-8")) > 512
        ):
            raise FormalTaskViolation(
                "INVALID_DURABILITY_OPERATOR",
                "durable recovery requires one bounded operator identity",
                ErrorCode.INVALID_ARGUMENT,
            )
        now = observed_at or utc_now()
        try:
            parsed_now = datetime.fromisoformat(now.replace("Z", "+00:00"))
            if parsed_now.tzinfo is None:
                raise ValueError
        except (TypeError, ValueError) as error:
            raise FormalTaskViolation(
                "INVALID_DURABILITY_TIME",
                "durable recovery time must be canonical UTC",
                ErrorCode.INVALID_ARGUMENT,
            ) from error
        expires_at = (
            (parsed_now + _OUTBOX_CLAIM_LEASE)
            .astimezone(UTC)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        authority = self.store.read_durable_recovery_authority(
            scope=scope, task_id=task_id
        )
        binding = self.store.read_durability_binding(
            scope=scope,
            task_id=task_id,
            origin_attempt_id=authority.producer_attempt.attempt_id,
        )
        owner_id = f"durability-recovery:{operator_id}:{uuid.uuid4().hex}"
        claim = self.store.claim_durability_mutator(
            scope=scope,
            task_id=task_id,
            owner_id=owner_id,
            observed_at=now,
            expires_at=expires_at,
        )
        if claim is None:
            raise FormalTaskViolation(
                "TASK_RECOVERY_MUTATOR_BUSY",
                "another durability mutator owns the Task",
                ErrorCode.UNAVAILABLE,
            )
        candidate_attempt_id = f"attempt-{uuid.uuid4().hex}"
        recovery_id = f"recovery-{uuid.uuid4().hex}"
        try:
            checkpoints = self.store.read_durability_checkpoints(binding)
            effects = self.store.read_durability_effects(binding)
            authorize = getattr(self.executor, "authorize_durable_recovery", None)
            if not callable(authorize):
                raise FormalTaskViolation(
                    "EXECUTOR_DURABILITY_UNAVAILABLE",
                    "Executor recovery facts are unavailable",
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                )
            facts, authorization = authorize(
                authority.task,
                authority.producer_attempt,
                recovery_id=recovery_id,
                candidate_recovery_attempt_id=candidate_attempt_id,
                profile=binding.profile,
                recovery_generation=authority.recovery_generation,
                checkpoint_head=checkpoints.head,
                checkpoint_prefix_digest=checkpoints.prefix_digest,
                effect_head=effects.head,
                effect_prefix_digest=effects.prefix_digest,
                claim_owner_id=owner_id,
                claim_token=claim[0],
                claim_generation=claim[1],
                observed_at=now,
                expires_at=expires_at,
            )
            if (
                type(facts) is not ExecutorRecoveryFacts
                or type(authorization) is not DurabilityMutationAuthorization
            ):
                raise FormalTaskViolation(
                    "EXECUTOR_RECOVERY_FACTS_INVALID",
                    "Executor recovery facts are not exact",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            return self.store.recover_durable_attempt(
                authority,
                recovery_id=recovery_id,
                recovery_facts=facts,
                checkpoint_head=checkpoints.head,
                checkpoint_prefix_digest=checkpoints.prefix_digest,
                effect_head=effects.head,
                effect_prefix_digest=effects.prefix_digest,
                authorization=authorization,
                observed_at=now,
                admission_policy=self._admission_policy,
            )
        except BaseException:
            self.store.release_durability_mutator(
                scope=scope,
                task_id=task_id,
                owner_id=owner_id,
                claim_token=claim[0],
                claim_generation=claim[1],
            )
            raise

    def read_current_retry_admission(
        self,
        *,
        scope: ScopeRef,
        task_id: str,
    ) -> TaskRetryAuthoritySnapshot:
        """Read the exact retry lineage and re-prove Executor quiescence.

        This is a side-effect-free admission preview.  ``execute`` repeats the
        same proof when it applies a retry, so a UI indication can never replace
        the authoritative mutation-time fence.
        """

        authority = self.read_current_retry_authority(scope=scope, task_id=task_id)
        try:
            readiness_method = getattr(self.executor, "retry_readiness", None)
            if not callable(readiness_method):
                raise AttributeError("retry_readiness is unavailable")
            readiness = readiness_method(authority.task, authority.attempt)
        except Exception as error:  # noqa: BLE001 -- fail closed at seam
            raise FormalTaskViolation(
                "TASK_RETRY_EXECUTOR_CLEANUP_PENDING",
                "Executor retry-readiness is unavailable",
                ErrorCode.UNAVAILABLE,
            ) from error
        self._require_retry_readiness(authority, readiness)
        return authority

    def read_applied_retry_replay(
        self,
        *,
        scope: ScopeRef,
        command_id: str,
        task_id: str,
        product_request: TaskRetryProductRequestFingerprint,
    ) -> AppliedTaskRetryReplay | None:
        """Expose durable replay before current admission/readiness evaluation."""

        return self.store.read_applied_retry_replay(
            scope=scope,
            command_id=command_id,
            task_id=task_id,
            product_request=product_request,
        )

    async def _publish_reconciliation_events(
        self,
        receipt: TaskMutationResult,
    ) -> None:
        """Publish only durable events appended by an actual reconciliation.

        Evidence is deliberately downstream of the Store transaction.  A sink
        failure can neither roll back nor reinterpret the Task/Attempt truth.
        """

        sink = self._reconciliation_event_sink
        if sink is None:
            return
        for event in receipt.events:
            try:
                await sink(event, receipt.attempt)
            except Exception:  # noqa: BLE001 -- evidence never owns Task truth
                continue

    def execute(
        self,
        command: CommandEnvelope,
        authorization: TaskAuthorizationGrant | None,
        *,
        context: ResolvedTaskContext | None = None,
        now: str | None = None,
        current_background_session_id: str | None = None,
        selection: PersistedExecutorSelection | None = None,
        admission_policy: AdmissionPolicy | None = None,
    ) -> ResultEnvelope:
        observed_at = now or utc_now()
        try:
            selected_policy = (
                None
                if selection is None
                else (
                    self._admission_policy
                    if admission_policy is None
                    else admission_policy
                )
            )
            if authorization is None:
                raise FormalTaskViolation(
                    "FORMAL_TASK_AUTHORIZATION_REQUIRED",
                    "formal task command requires trusted authorization",
                    ErrorCode.UNAUTHENTICATED,
                )
            if command.command_type not in {
                "task.create",
                "task.cancel",
                "task.retry",
                "task.adjust",
                "task.update",
                "task.provide_input",
                "task.pause",
                "task.resume",
                "task.reprioritize",
                "task.create_successor",
                "task.ack_events",
            }:
                raise FormalTaskViolation(
                    "UNSUPPORTED_FORMAL_TASK_COMMAND",
                    "formal Task Core does not support this command",
                    ErrorCode.UNSUPPORTED,
                )
            if command.target_ref.kind != "task":
                raise FormalTaskViolation(
                    "FORMAL_TASK_TARGET_MISMATCH",
                    "formal task commands require a task target reference",
                    ErrorCode.INVALID_ARGUMENT,
                )
            expected_target_id = (
                f"create:{command.command_id}"
                if command.command_type == "task.create"
                else command.target_ref.id
            )
            if command.target_ref.id != expected_target_id:
                raise FormalTaskViolation(
                    "FORMAL_TASK_TARGET_MISMATCH",
                    "task.create target must bind the exact command identity",
                    ErrorCode.INVALID_ARGUMENT,
                )
            expected_capabilities = frozenset({command.command_type})
            if frozenset(command.required_capabilities) != expected_capabilities:
                raise FormalTaskViolation(
                    "FORMAL_TASK_CAPABILITY_MISMATCH",
                    "formal task command must require its exact operation capability",
                    ErrorCode.PERMISSION_DENIED,
                )
            target_task_id = (
                None if command.command_type == "task.create" else command.target_ref.id
            )
            authorization.authorize(
                scope=command.scope,
                operation=command.command_type,
                command_id=command.command_id,
                target_task_id=target_task_id,
                required_capabilities=expected_capabilities,
                destructive=True,
                now=observed_at,
            )
            if command.command_type == "task.ack_events":
                require_exact_payload(
                    command.payload,
                    frozenset(
                        {
                            "presentation_class",
                            "acked_through_seq",
                            "acked_event_id",
                            "expected_event_head",
                        }
                    ),
                    field_name="task.ack_events payload",
                )
                return self.store.ack_events(command, observed_at=observed_at)
            if command.command_type == "task.cancel":
                require_exact_payload(
                    command.payload, frozenset(), field_name="task.cancel payload"
                )
                return self.store.cancel(command, observed_at=observed_at)
            if command.command_type in {
                "task.provide_input",
                "task.pause",
                "task.resume",
                "task.reprioritize",
            }:
                expected_payload = {
                    "task.provide_input": frozenset(
                        {
                            "attempt_id",
                            "expected_event_head",
                            "responds_to_event_id",
                            "text",
                        }
                    ),
                    "task.pause": frozenset(
                        {"attempt_id", "expected_event_head", "reason"}
                    ),
                    "task.resume": frozenset(
                        {"attempt_id", "expected_event_head", "reason"}
                    ),
                    "task.reprioritize": frozenset(
                        {"attempt_id", "expected_event_head", "priority", "reason"}
                    ),
                }[command.command_type]
                require_exact_payload(
                    command.payload,
                    expected_payload,
                    field_name=f"{command.command_type} payload",
                )
                if command.command_type == "task.reprioritize":
                    return self.store.reprioritize(command, observed_at=observed_at)
                return self.store.decide_unsupported_control(
                    command, observed_at=observed_at
                )
            if command.command_type == "task.create_successor":
                require_exact_payload(
                    command.payload,
                    self._SUCCESSOR_PAYLOAD,
                    field_name="task.create_successor payload",
                )
                if context is None:
                    raise FormalTaskViolation(
                        "FORMAL_TASK_CONTEXT_REQUIRED",
                        "task.create_successor requires server-resolved context",
                        ErrorCode.PERMISSION_DENIED,
                    )
                context.require_usable(
                    scope=command.scope,
                    required_permissions=frozenset({"task.execute", "project.write"}),
                    destructive=True,
                    now=observed_at,
                )
                attributes = command.payload["attributes"]
                if (
                    type(attributes) is not dict
                    or set(attributes) != {"model_identity", "model_config_version"}
                    or any(
                        type(key) is not str or type(value) is not str
                        for key, value in attributes.items()
                    )
                ):
                    raise FormalTaskViolation(
                        "INVALID_FORMAL_TASK_ATTRIBUTES",
                        "successor requires an exact resolved model binding",
                        ErrorCode.INVALID_ARGUMENT,
                    )
                spec = FormalTaskSpec(
                    name=command.payload["name"],
                    instruction=command.payload["instruction"],
                    origin=command.origin,
                    context=context,
                    executor_id=command.payload["executor_id"],
                    required_capabilities=tuple(command.required_capabilities),
                    side_effect_class=command.payload["side_effect_class"],
                    constraints=tuple(command.payload["constraints"]),
                    attributes=tuple(sorted(attributes.items())),
                )
                if spec.executor_id != self.executor.executor_id:
                    raise FormalTaskViolation(
                        "EXECUTOR_CAPABILITY_UNAVAILABLE",
                        "requested Executor is not available in this Task Core",
                        ErrorCode.CAPABILITY_UNAVAILABLE,
                    )
                if spec.side_effect_class != "project_mutation":
                    raise FormalTaskViolation(
                        "EXECUTOR_SIDE_EFFECT_CLASS_MISMATCH",
                        "project Code Agent tasks require project_mutation side effects",
                        ErrorCode.CAPABILITY_UNAVAILABLE,
                    )
                return self.store.create_successor(
                    command,
                    spec,
                    observed_at=observed_at,
                    selection=selection,
                    admission_policy=selected_policy,
                )
            if command.command_type == "task.update":
                require_exact_payload(
                    command.payload,
                    frozenset(
                        {
                            "attempt_id",
                            "expected_event_head",
                            "instruction",
                            "constraints",
                        }
                    ),
                    field_name="task.update payload",
                )
                return self.store.update(command, observed_at=observed_at)
            if command.command_type == "task.adjust":
                require_exact_payload(
                    command.payload,
                    frozenset({"adjustment"}),
                    field_name="task.adjust payload",
                )
                return self.store.adjust(
                    command,
                    observed_at=observed_at,
                )
            if command.command_type == "task.retry":
                authority_or_replay = self.store.read_retry_authority(
                    command,
                    observed_at=observed_at,
                    selection=selection,
                )
                if isinstance(authority_or_replay, ResultEnvelope):
                    return authority_or_replay
                authority = authority_or_replay
                if context is None:
                    raise FormalTaskViolation(
                        "FORMAL_TASK_CONTEXT_REQUIRED",
                        "task.retry requires a server-resolved execution context",
                        ErrorCode.PERMISSION_DENIED,
                    )
                spec = replace(authority.task.spec, context=context)
                self._validate_retry_context(authority, context, observed_at)
                try:
                    readiness_method = getattr(self.executor, "retry_readiness", None)
                    if not callable(readiness_method):
                        raise AttributeError("retry_readiness is unavailable")
                    readiness = readiness_method(authority.task, authority.attempt)
                except Exception as error:  # noqa: BLE001 -- fail closed at seam
                    raise FormalTaskViolation(
                        "TASK_RETRY_EXECUTOR_CLEANUP_PENDING",
                        "Executor retry-readiness is unavailable",
                        ErrorCode.UNAVAILABLE,
                    ) from error
                self._require_retry_readiness(authority, readiness)
                return self.store.retry(
                    command,
                    spec,
                    authority,
                    observed_at=observed_at,
                    selection=selection,
                    admission_policy=selected_policy,
                )
            if context is None:
                raise FormalTaskViolation(
                    "FORMAL_TASK_CONTEXT_REQUIRED",
                    "task.create requires a server-resolved execution context",
                    ErrorCode.PERMISSION_DENIED,
                )
            context.require_usable(
                scope=command.scope,
                required_permissions=frozenset({"task.execute", "project.write"}),
                destructive=True,
                now=observed_at,
            )
            payload = command.payload
            require_exact_payload(
                payload, self._CREATE_PAYLOAD, field_name="task.create payload"
            )
            attributes = payload["attributes"]
            if type(attributes) is not dict or any(
                type(key) is not str or type(value) is not str
                for key, value in attributes.items()
            ):
                raise FormalTaskViolation(
                    "INVALID_FORMAL_TASK_ATTRIBUTES",
                    "task attributes must be a string map",
                    ErrorCode.INVALID_ARGUMENT,
                )
            if set(attributes) != {"model_identity", "model_config_version"}:
                raise FormalTaskViolation(
                    "INVALID_FORMAL_TASK_ATTRIBUTES",
                    "project Code Agent tasks require an exact resolved model binding",
                    ErrorCode.INVALID_ARGUMENT,
                )
            spec = FormalTaskSpec(
                name=payload["name"],
                instruction=payload["instruction"],
                origin=command.origin,
                context=context,
                executor_id=payload["executor_id"],
                required_capabilities=tuple(command.required_capabilities),
                side_effect_class=payload["side_effect_class"],
                attributes=tuple(sorted(attributes.items())),
            )
            if spec.executor_id != self.executor.executor_id:
                raise FormalTaskViolation(
                    "EXECUTOR_CAPABILITY_UNAVAILABLE",
                    "requested Executor is not available in this Task Core",
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                )
            if spec.side_effect_class != "project_mutation":
                raise FormalTaskViolation(
                    "EXECUTOR_SIDE_EFFECT_CLASS_MISMATCH",
                    "project Code Agent tasks require project_mutation side effects",
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                )
            return self.store.create(
                command,
                spec,
                observed_at=observed_at,
                current_background_session_id=current_background_session_id,
                selection=selection,
                admission_policy=selected_policy,
            )
        except FormalTaskViolation as error:
            return _failure(command, error, observed_at=observed_at)

    @staticmethod
    def _validate_retry_context(
        authority: TaskRetryAuthoritySnapshot,
        context: ResolvedTaskContext,
        observed_at: str,
    ) -> None:
        context.require_usable(
            scope=authority.task.scope,
            required_permissions=frozenset({"task.execute", "project.write"}),
            destructive=True,
            now=observed_at,
        )
        prior = authority.task.spec.context
        if (
            context.source,
            context.stable_id,
            context.uri,
            context.scope,
        ) != (
            prior.source,
            prior.stable_id,
            prior.uri,
            prior.scope,
        ):
            raise FormalTaskViolation(
                "TASK_RETRY_CONTEXT_IDENTITY_MISMATCH",
                "retry context must preserve the task's stable project identity",
                ErrorCode.PERMISSION_DENIED,
            )

    @staticmethod
    def _require_retry_readiness(
        authority: TaskRetryAuthoritySnapshot,
        readiness: object,
    ) -> None:
        if type(readiness) is not ExecutorRetryReadiness:
            raise FormalTaskViolation(
                "TASK_RETRY_EXECUTOR_CLEANUP_PENDING",
                "Executor retry-readiness response is unavailable",
                ErrorCode.UNAVAILABLE,
            )
        attempt = authority.attempt
        if (
            readiness.task_id != authority.task.task_id
            or readiness.previous_attempt_id != attempt.attempt_id
            or readiness.previous_outcome != attempt.outcome
            or readiness.previous_attempt_number != attempt.attempt_number
        ):
            raise FormalTaskViolation(
                "TASK_RETRY_EXECUTOR_READINESS_MISMATCH",
                "Executor retry-readiness evidence binds another attempt",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if not readiness.ready:
            raise FormalTaskViolation(
                "TASK_RETRY_EXECUTOR_CLEANUP_PENDING",
                "Executor predecessor cleanup is not retry-ready",
                ErrorCode.UNAVAILABLE,
            )

    @staticmethod
    def _task_read_projection(
        task: PersistentTaskRecord,
        admission: PersistentAdmissionRecord | None,
    ) -> tuple[dict[str, object], dict[str, object] | None]:
        admission_payload = None if admission is None else admission.to_dict()
        task_payload = task.to_dict()
        task_payload["queued"] = bool(admission is not None and admission.queued)
        task_payload["admission"] = admission_payload
        return task_payload, admission_payload

    def query(
        self,
        query: QueryEnvelope,
        authorization: TaskAuthorizationGrant | None,
        *,
        now: str | None = None,
    ) -> ResultEnvelope:
        observed_at = now or utc_now()
        try:
            if authorization is None:
                raise FormalTaskViolation(
                    "FORMAL_TASK_AUTHORIZATION_REQUIRED",
                    "formal task query requires trusted authorization",
                    ErrorCode.UNAUTHENTICATED,
                )
            if query.target_ref.kind != "task":
                raise FormalTaskViolation(
                    "FORMAL_TASK_TARGET_MISMATCH",
                    "formal task queries require a task target reference",
                    ErrorCode.INVALID_ARGUMENT,
                )
            target_task_id = (
                None if query.query_type == "task.list" else query.target_ref.id
            )
            expected_capabilities = frozenset({query.query_type})
            if frozenset(query.required_capabilities) != expected_capabilities:
                raise FormalTaskViolation(
                    "FORMAL_TASK_CAPABILITY_MISMATCH",
                    "formal task query must require its exact operation capability",
                    ErrorCode.PERMISSION_DENIED,
                )
            authorization.authorize(
                scope=query.scope,
                operation=query.query_type,
                command_id=None,
                target_task_id=target_task_id,
                required_capabilities=expected_capabilities,
                destructive=False,
                now=observed_at,
            )
            if query.query_type == "task.list":
                if query.target_ref.id != "task-list":
                    raise FormalTaskViolation(
                        "FORMAL_TASK_TARGET_MISMATCH",
                        "task.list requires its canonical collection target",
                        ErrorCode.INVALID_ARGUMENT,
                    )
                payload = query.payload
                if set(payload) - {"cursor", "limit"}:
                    raise FormalTaskViolation(
                        "INVALID_TASK_LIST_QUERY",
                        "task.list query has unknown payload fields",
                        ErrorCode.INVALID_ARGUMENT,
                    )
                cursor = payload.get("cursor")
                limit = payload.get("limit", 50)
                snapshots, next_cursor, has_more = (
                    self.store.list_task_read_snapshots_page(
                        query.scope,
                        cursor=cursor,
                        limit=limit,
                    )
                )
                projected_tasks = [
                    self._task_read_projection(task, admission)[0]
                    for task, _attempt, admission in snapshots
                ]
                result: Mapping[str, object] = {
                    "tasks": projected_tasks,
                    "cursor": cursor,
                    "next_cursor": next_cursor,
                    "has_more": has_more,
                    "limit": limit,
                }
            elif query.query_type in {"task.get", "task.status"}:
                require_exact_payload(
                    query.payload,
                    frozenset(),
                    field_name=f"{query.query_type} payload",
                )
                task, attempt, admission = self.store.task_read_snapshot(
                    query.target_ref.id, query.scope
                )
                task_payload, admission_payload = self._task_read_projection(
                    task, admission
                )
                result = {
                    "task": task_payload,
                    "attempt": attempt.to_dict(),
                    "admission": admission_payload,
                }
            elif query.query_type == "task.events":
                payload = query.payload
                if set(payload) - {"after_seq", "limit"}:
                    raise FormalTaskViolation(
                        "INVALID_TASK_EVENTS_QUERY",
                        "task.events query has unknown payload fields",
                        ErrorCode.INVALID_ARGUMENT,
                    )
                after_seq = payload.get("after_seq", -1)
                limit = payload.get("limit", 100)
                events, head_seq, next_after_seq, has_more = self.store.events_page(
                    query.target_ref.id,
                    query.scope,
                    after_seq=after_seq,
                    limit=limit,
                )
                result = {
                    "task_id": query.target_ref.id,
                    "after_seq": after_seq,
                    "events": [event.to_dict() for event in events],
                    "head_seq": head_seq,
                    "next_after_seq": next_after_seq,
                    "has_more": has_more,
                    "limit": limit,
                    "truncated": has_more,
                    "cursor_replay_supported": True,
                }
            elif query.query_type == "task.unread_events":
                require_exact_payload(
                    query.payload,
                    frozenset({"presentation_class", "limit"}),
                    field_name="task.unread_events payload",
                )
                page = self.store.unread_events_page(
                    query.target_ref.id,
                    query.scope,
                    presentation_class=query.payload["presentation_class"],
                    limit=query.payload["limit"],
                )
                result = page.to_dict()
            elif query.query_type == "task.result":
                require_exact_payload(
                    query.payload,
                    frozenset(),
                    field_name="task.result payload",
                )
                availability, record, reason = self.store.task_result(
                    query.target_ref.id,
                    query.scope,
                )
                result = {
                    "task_id": query.target_ref.id,
                    "availability": availability.value,
                    "reason": reason,
                    "task_result": (
                        record.to_dict()
                        if availability is TaskResultAvailability.AVAILABLE
                        and record is not None
                        else None
                    ),
                }
            else:
                raise FormalTaskViolation(
                    "UNSUPPORTED_FORMAL_TASK_QUERY",
                    "formal P3-alpha query is unsupported",
                    ErrorCode.UNSUPPORTED,
                )
            return ResultEnvelope.success(
                owner=query,
                result=result,
                observed_at=observed_at,
            )
        except FormalTaskViolation as error:
            return _failure(query, error, observed_at=observed_at)

    async def drain_outbox_once(
        self,
        *,
        worker_id: str | None = None,
        observed_at: str | None = None,
    ) -> bool:
        worker = worker_id or f"task-core-{uuid.uuid4().hex}"
        item = self.store.claim_outbox(worker, observed_at=observed_at)
        if item is None:
            return False
        try:
            if item.kind is OutboxKind.ATTEMPT_DISPATCH:
                delivery = await self.executor.dispatch(item)
            elif item.kind is OutboxKind.ATTEMPT_CANCEL:
                delivery = await self.executor.cancel(item)
            else:
                adjustment_delivery = await self.executor.adjust(item)
        except FormalTaskViolation as error:
            if (
                item.kind is OutboxKind.ATTEMPT_DISPATCH
                and item.selection is not None
                and error.code is ErrorCode.UNAVAILABLE
                and error.reason
                in {"EXECUTOR_PROJECT_BUSY", "EXECUTOR_CAPACITY_EXHAUSTED"}
            ):
                self.store.defer_admission(
                    item,
                    reason=error.reason,
                    policy=self._admission_policy,
                    observed_at=observed_at or utc_now(),
                )
                return True
            if item.kind is OutboxKind.ATTEMPT_ADJUST and error.code not in {
                ErrorCode.UNAVAILABLE,
                ErrorCode.TIMEOUT,
                ErrorCode.RESULT_UNKNOWN,
            }:
                assert item.executor_ref is not None
                adjustment_delivery = TaskAdjustmentDeliveryResult(
                    item.executor_ref,
                    item.command_id,
                    TaskAdjustmentState.REJECTED,
                    canonical_task_adjustment_rejection_reason(error.reason),
                )
            elif error.code in {
                ErrorCode.UNAVAILABLE,
                ErrorCode.TIMEOUT,
                ErrorCode.RESULT_UNKNOWN,
            }:
                self.store.release_outbox(item, str(error))
                raise
            else:
                self.store.reject_outbox(item, error)
                return True
        except Exception as error:
            self.store.release_outbox(item, str(error))
            raise
        if item.kind is OutboxKind.ATTEMPT_ADJUST:
            try:
                settlement = self.store.complete_adjustment_outbox(
                    item,
                    adjustment_delivery,
                )
            except FormalTaskViolation as error:
                rejected = TaskAdjustmentSettlement(
                    TaskAdjustmentState.REJECTED,
                    False,
                )
                await self.executor.settle_adjustment(item, rejected)
                try:
                    self.store.release_outbox(item, str(error))
                except FormalTaskViolation:
                    pass
                raise FormalTaskViolation(
                    error.reason,
                    "Executor adjustment exists but Core rejected its evidence",
                    ErrorCode.RESULT_UNKNOWN,
                ) from error
            await self.executor.settle_adjustment(item, settlement)
            return True
        if item.kind is OutboxKind.ATTEMPT_DISPATCH and not delivery.observations:
            self.store.release_outbox(
                item, "dispatch returned no accepted Executor evidence"
            )
            raise FormalTaskViolation(
                "EXECUTOR_DISPATCH_RESULT_UNKNOWN",
                "dispatched attempt exists but accepted evidence is unavailable",
                ErrorCode.RESULT_UNKNOWN,
            )
        try:
            self.store.complete_outbox(
                item,
                executor_ref=delivery.executor_ref,
                observations=delivery.observations,
            )
        except FormalTaskViolation as error:
            self.store.release_outbox(item, str(error))
            raise FormalTaskViolation(
                error.reason,
                f"Executor delivery exists but Core rejected its evidence: {error}",
                ErrorCode.RESULT_UNKNOWN,
            ) from error
        return True

    async def drain_outbox(self, *, worker_id: str | None = None) -> int:
        delivered = 0
        worker = worker_id or f"task-core-{uuid.uuid4().hex}"
        while await self.drain_outbox_once(worker_id=worker):
            delivered += 1
        return delivered

    async def reconcile(self) -> dict[str, int]:
        """Resolve only original attempts; never creates a replacement attempt."""

        claimed_before = (
            (datetime.now(UTC) - _OUTBOX_CLAIM_LEASE).isoformat().replace("+00:00", "Z")
        )
        reset_claims = self.store.reset_expired_outbox_claims(
            claimed_before=claimed_before
        )
        delivered = delivery_unavailable = 0
        while True:
            try:
                changed = await self.drain_outbox_once(worker_id="task-core-restart")
            except Exception:  # noqa: BLE001 -- one delivery cannot abort restart audit
                delivery_unavailable += 1
                break
            if not changed:
                break
            delivered += 1
        status_summary = await self.reconcile_status()
        return {
            "reset_claims": reset_claims,
            "delivered": delivered,
            "delivery_unavailable": delivery_unavailable,
            **status_summary,
        }

    async def reconcile_status(self) -> dict[str, int]:
        """Consume only Executor status evidence for canonical nonterminal attempts."""

        known = unavailable = lost = superseded = 0
        for task, attempt in self.store.nonterminal_attempts():
            if attempt.executor_ref is None:
                receipt = self.store.mark_reconciliation_pending(
                    task.task_id, attempt.attempt_id, "ATTEMPT_NOT_YET_BOUND"
                )
                if receipt.disposition is TaskMutationDisposition.SUPERSEDED:
                    superseded += 1
                    continue
                unavailable += 1
                continue
            receipt = self.store.mark_reconciliation_pending(
                task.task_id,
                attempt.attempt_id,
                "EXECUTOR_STATUS_QUERY",
                in_progress=True,
            )
            if receipt.disposition is TaskMutationDisposition.SUPERSEDED:
                superseded += 1
                continue
            try:
                resolution = await self.executor.status(task, attempt)
            except Exception as error:  # noqa: BLE001 -- isolate one Executor attempt
                receipt = self.store.mark_reconciliation_pending(
                    task.task_id,
                    attempt.attempt_id,
                    f"EXECUTOR_STATUS_ERROR: {error}"[:1000],
                )
                if receipt.disposition is TaskMutationDisposition.SUPERSEDED:
                    superseded += 1
                    continue
                unavailable += 1
                continue
            if isinstance(resolution, ExecutorDeliveryResult):
                if resolution.executor_ref != attempt.executor_ref:
                    receipt = self.store.mark_reconciliation_pending(
                        task.task_id,
                        attempt.attempt_id,
                        "EXECUTOR_STATUS_BINDING_MISMATCH",
                    )
                    if receipt.disposition is TaskMutationDisposition.SUPERSEDED:
                        superseded += 1
                        continue
                    unavailable += 1
                    continue
                if not resolution.observations:
                    if attempt.selection is not None:
                        receipt = self.store.mark_reconciliation_pending(
                            task.task_id,
                            attempt.attempt_id,
                            "EXECUTOR_STATUS_SELECTION_PROOF_REQUIRED",
                        )
                        if receipt.disposition is TaskMutationDisposition.SUPERSEDED:
                            superseded += 1
                            continue
                        unavailable += 1
                        continue
                    receipt = self.store.mark_reconciliation_resolved(
                        task.task_id,
                        attempt.attempt_id,
                        "EXECUTOR_STATE_UNCHANGED",
                    )
                    if receipt.disposition is TaskMutationDisposition.SUPERSEDED:
                        superseded += 1
                        continue
                    known += 1
                    continue
                observations = resolution.observations
            elif isinstance(resolution, ExecutorObservation):
                observations = (resolution,)
            else:
                receipt = self.store.mark_reconciliation_pending(
                    task.task_id,
                    attempt.attempt_id,
                    "EXECUTOR_STATUS_PROTOCOL_VIOLATION",
                )
                if receipt.disposition is TaskMutationDisposition.SUPERSEDED:
                    superseded += 1
                    continue
                unavailable += 1
                continue
            final = observations[-1]
            if (
                final.task_id != task.task_id
                or final.attempt_id != attempt.attempt_id
                or final.executor_id != attempt.executor_id
                or final.executor_ref != attempt.executor_ref
            ):
                receipt = self.store.mark_reconciliation_pending(
                    task.task_id,
                    attempt.attempt_id,
                    "EXECUTOR_STATUS_BINDING_MISMATCH",
                )
                if receipt.disposition is TaskMutationDisposition.SUPERSEDED:
                    superseded += 1
                    continue
                unavailable += 1
                continue
            expected_selection_binding = (
                (None, None)
                if attempt.selection is None
                else (
                    attempt.selection.adapter_id,
                    attempt.selection.capability_profile_digest,
                )
            )
            if any(
                (
                    observation.adapter_id,
                    observation.capability_profile_digest,
                )
                != expected_selection_binding
                for observation in observations
            ):
                receipt = self.store.mark_reconciliation_pending(
                    task.task_id,
                    attempt.attempt_id,
                    "EXECUTOR_STATUS_SELECTION_MISMATCH",
                )
                if receipt.disposition is TaskMutationDisposition.SUPERSEDED:
                    superseded += 1
                    continue
                unavailable += 1
                continue
            if final.resolution is ExecutorResolution.KNOWN:
                try:
                    receipt = self.store.apply_observations(observations)
                except FormalTaskViolation as error:
                    if error.code is ErrorCode.INTERNAL:
                        raise
                    receipt = self.store.mark_reconciliation_pending(
                        task.task_id,
                        attempt.attempt_id,
                        f"EXECUTOR_EVIDENCE_REJECTED: {error.reason}",
                    )
                    if receipt.disposition is TaskMutationDisposition.SUPERSEDED:
                        superseded += 1
                        continue
                    unavailable += 1
                else:
                    if receipt.disposition is TaskMutationDisposition.SUPERSEDED:
                        superseded += 1
                        continue
                    known += 1
                    await self._publish_reconciliation_events(receipt)
            elif final.resolution is ExecutorResolution.LOST:
                receipt = self.store.resolve_lost_attempt(
                    task.task_id,
                    attempt.attempt_id,
                    final.error or "EXECUTOR_ATTEMPT_LOST",
                )
                if receipt.disposition is TaskMutationDisposition.SUPERSEDED:
                    superseded += 1
                    continue
                lost += 1
                await self._publish_reconciliation_events(receipt)
            else:
                receipt = self.store.mark_reconciliation_pending(
                    task.task_id,
                    attempt.attempt_id,
                    final.error or "EXECUTOR_STATUS_UNAVAILABLE",
                )
                if receipt.disposition is TaskMutationDisposition.SUPERSEDED:
                    superseded += 1
                    continue
                unavailable += 1
        return {
            "known": known,
            "unavailable": unavailable,
            "lost": lost,
            "superseded": superseded,
        }


__all__ = [
    "FormalExecutor",
    "PersistentTaskCore",
    "ReconciliationEventSink",
    "project_task_event",
]
