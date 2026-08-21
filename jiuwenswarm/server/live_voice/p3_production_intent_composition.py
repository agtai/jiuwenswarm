# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Authenticated product composition for generalized P3 Task intents.

This module adapts existing authorities; it does not own a second commit,
confirmation, Task, Result, capability, or command ledger.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from threading import RLock

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ContractViolation,
    ErrorCode,
    OriginRef,
    ScopeRef,
    TerminalOutcome,
    TurnCommitLedger,
    canonical_json_bytes,
)

from .executor_capabilities import ExecutorCapabilityProfile
from .formal_task_models import (
    FormalAttemptState,
    FormalTaskState,
    FormalTaskViolation,
    PersistentAdmissionRecord,
    PersistentAttemptRecord,
    PersistentTaskRecord,
    TaskResultAvailability,
)
from .p3_confirmation import (
    P3ConfirmationBinding,
    SqliteP3ConfirmationLedger,
    ValidatedP3ConfirmationForwarding,
    VerifiedP3Confirmation,
)
from .p3_product_confirmation import ProductP3ConfirmationForwarder
from .production_task_intent import (
    AuthenticatedTaskFact,
    ProductionConfirmationBinding,
    ProductionIntentOrigin,
    ProductionOriginBinding,
    ProductionTaskPolicyOutcome,
    ProductionTaskResolution,
    TaskAuthorityRead,
    TrustedConfirmationConsumptionReceipt,
    TrustedProductionOriginReceipt,
)
from .task_core import AttemptState, TaskState
from .task_store import SqliteTaskStore


_QUERY_OPERATIONS = frozenset(
    {"task.get", "task.list", "task.status", "task.events", "task.result"}
)
_NO_EXECUTOR_PROFILE_DIGEST = hashlib.sha256(
    canonical_json_bytes(
        {
            "authority": "live_voice.production_task_reader",
            "fact": "no_executor_selection",
            "version": 1,
        }
    )
).hexdigest()


def _reader_violation(
    reason: str,
    message: str,
    code: ErrorCode = ErrorCode.PROTOCOL_VIOLATION,
) -> FormalTaskViolation:
    return FormalTaskViolation(reason, message, code)


@dataclass(frozen=True, slots=True)
class CallLocalProductionConfirmationClaim:
    """Private in-process authority transferred once to Core composition."""

    verified: VerifiedP3Confirmation
    p3_binding: P3ConfirmationBinding
    production_binding: ProductionConfirmationBinding
    consumption_id: str
    resolution_fingerprint: str


class CallLocalProductionConfirmationConsumer:
    """Consume one durable P3 confirmation and expose one exact local claim.

    The resolver-facing receipt is intentionally insufficient for invoking
    Core.  Only this instance retains the real verified ledger fact and may
    yield it once after checking the final immutable resolution.
    """

    def __init__(
        self,
        *,
        expected_binding: ProductionConfirmationBinding,
        validated: ValidatedP3ConfirmationForwarding,
        forwarder: ProductP3ConfirmationForwarder,
        now: str,
    ) -> None:
        if not isinstance(expected_binding, ProductionConfirmationBinding):
            raise TypeError("PRODUCTION_CONFIRMATION_BINDING_REQUIRED")
        if type(validated) is not ValidatedP3ConfirmationForwarding:
            raise TypeError("VALIDATED_P3_CONFIRMATION_FORWARDING_REQUIRED")
        if type(forwarder) is not ProductP3ConfirmationForwarder:
            raise TypeError("PRODUCT_P3_CONFIRMATION_FORWARDER_REQUIRED")
        if type(now) is not str or not now:
            raise TypeError("PRODUCTION_CONFIRMATION_TIME_REQUIRED")
        p3_binding = P3ConfirmationBinding(
            principal_id=expected_binding.principal_id,
            scope=expected_binding.scope,
            operation=expected_binding.operation,
            command_id=expected_binding.command_id,
            target_task_id=expected_binding.target_task_id,
            intent_fingerprint=expected_binding.fingerprint,
        )
        if validated.binding != p3_binding:
            raise _reader_violation(
                "PRODUCTION_CONFIRMATION_FORWARDING_MISMATCH",
                "validated P3 confirmation does not bind the production intent",
                ErrorCode.PERMISSION_DENIED,
            )
        self._expected = expected_binding
        self._p3_binding = p3_binding
        self._validated = validated
        self._forwarder = forwarder
        self._now = now
        self._lock = RLock()
        self._consume_attempted = False
        self._verified: VerifiedP3Confirmation | None = None
        self._consumption_id: str | None = None
        self._claimed = False

    def bound_to_verifier(self, verifier: object) -> bool:
        """Prove that this claim consumes the composition's configured ledger."""

        if type(verifier) is ProductP3ConfirmationForwarder:
            return self._forwarder is verifier
        if type(verifier) is SqliteP3ConfirmationLedger:
            owner_verifier = self._forwarder.owner.raw_verifier
            return bool(
                type(owner_verifier) is SqliteP3ConfirmationLedger
                and owner_verifier.database_path.resolve()
                == verifier.database_path.resolve()
            )
        return False

    def verify_and_consume(
        self,
        confirmation_id: str,
        binding: ProductionConfirmationBinding,
    ) -> TrustedConfirmationConsumptionReceipt:
        if (
            confirmation_id != self._validated.confirmation_id
            or binding != self._expected
        ):
            raise _reader_violation(
                "PRODUCTION_CONFIRMATION_BINDING_MISMATCH",
                "confirmation does not match the exact call-local production binding",
                ErrorCode.PERMISSION_DENIED,
            )
        with self._lock:
            if self._consume_attempted:
                raise _reader_violation(
                    "PRODUCTION_CONFIRMATION_CONSUME_REPLAY",
                    "call-local production confirmation was already attempted",
                    ErrorCode.CONFLICT,
                )
            self._consume_attempted = True
        with self._forwarder.permit(self._validated):
            verified = self._forwarder.verify_and_consume(
                confirmation_id,
                self._p3_binding,
                now=self._now,
            )
        if verified.replayed:
            raise _reader_violation(
                "PRODUCTION_CONFIRMATION_ALREADY_CONSUMED",
                "durable production confirmation was already consumed",
                ErrorCode.CONFLICT,
            )
        consumption_id = (
            "production-confirmation."
            + hashlib.sha256(
                canonical_json_bytes(
                    {
                        "binding": self._expected.fingerprint,
                        "confirmation_id": verified.confirmation_id,
                        "expires_at": verified.expires_at,
                    }
                )
            ).hexdigest()
        )
        with self._lock:
            self._verified = verified
            self._consumption_id = consumption_id
        return TrustedConfirmationConsumptionReceipt(
            confirmation_id=verified.confirmation_id,
            consumption_id=consumption_id,
            binding_fingerprint=self._expected.fingerprint,
            replayed=False,
        )

    def claim_for(
        self,
        resolution: ProductionTaskResolution,
    ) -> CallLocalProductionConfirmationClaim:
        if not isinstance(resolution, ProductionTaskResolution):
            raise TypeError("PRODUCTION_TASK_RESOLUTION_REQUIRED")
        with self._lock:
            verified = self._verified
            consumption_id = self._consumption_id
            if verified is None or consumption_id is None:
                raise _reader_violation(
                    "PRODUCTION_CONFIRMATION_NOT_CONSUMED",
                    "Core composition requires a consumed durable confirmation",
                    ErrorCode.PERMISSION_DENIED,
                )
            if self._claimed:
                raise _reader_violation(
                    "PRODUCTION_CONFIRMATION_CLAIM_REPLAY",
                    "call-local production confirmation claim is single use",
                    ErrorCode.CONFLICT,
                )
            expected = self._expected
            if (
                resolution.outcome is not ProductionTaskPolicyOutcome.PROPOSED
                or resolution.confirmation != "confirmed"
                or resolution.confirmation_binding != expected
                or resolution.confirmation_consumption_id != consumption_id
                or resolution.command_id != expected.command_id
                or resolution.operation != expected.operation
                or resolution.target_task_id != expected.target_task_id
                or resolution.origin_receipt_id != expected.origin_receipt_id
                or resolution.origin_binding_fingerprint
                != expected.origin_binding_fingerprint
                or resolution.task_set_fingerprint != expected.task_set_fingerprint
                or hashlib.sha256(
                    canonical_json_bytes(dict(resolution.arguments))
                ).hexdigest()
                != expected.arguments_sha256
            ):
                raise _reader_violation(
                    "PRODUCTION_CONFIRMATION_RESOLUTION_MISMATCH",
                    "consumed confirmation does not bind the final production resolution",
                    ErrorCode.PERMISSION_DENIED,
                )
            self._claimed = True
            return CallLocalProductionConfirmationClaim(
                verified=verified,
                p3_binding=self._p3_binding,
                production_binding=expected,
                consumption_id=consumption_id,
                resolution_fingerprint=resolution.fingerprint,
            )


class StoreProductionTaskAuthorityReader:
    """Project authenticated Store facts into the production resolver Port.

    The adapter is deliberately read-only and bounded.  One complete visible
    set is read twice around the auxiliary event/result reads, so no Task-set,
    lifecycle, capability or lineage drift can be labelled one authority
    generation.
    """

    def __init__(
        self,
        *,
        store: SqliteTaskStore,
        principal_id: str,
        scope: ScopeRef,
        visible_task_capacity: int = 32,
        collection_capability_profile_digest: str = _NO_EXECUTOR_PROFILE_DIGEST,
    ) -> None:
        if not isinstance(store, SqliteTaskStore):
            raise TypeError("PRODUCTION_TASK_STORE_REQUIRED")
        if type(principal_id) is not str or not principal_id:
            raise TypeError("PRODUCTION_TASK_PRINCIPAL_REQUIRED")
        if (
            not isinstance(scope, ScopeRef)
            or scope.assurance is not Assurance.AUTHENTICATED
            or scope.subject_id != principal_id
        ):
            raise ValueError("PRODUCTION_TASK_AUTHORITY_SCOPE_MISMATCH")
        if (
            type(visible_task_capacity) is not int
            or not 1 <= visible_task_capacity <= 32
        ):
            raise ValueError("INVALID_PRODUCTION_TASK_AUTHORITY_CAPACITY")
        if (
            type(collection_capability_profile_digest) is not str
            or len(collection_capability_profile_digest) != 64
            or any(
                character not in "0123456789abcdef"
                for character in collection_capability_profile_digest
            )
        ):
            raise ValueError("INVALID_COLLECTION_CAPABILITY_PROFILE_DIGEST")
        self._store = store
        self._principal_id = principal_id
        self._scope = scope
        self._capacity = visible_task_capacity
        self._collection_capability_profile_digest = (
            collection_capability_profile_digest
        )

    def _require_scope(self, scope: ScopeRef) -> None:
        if (
            not isinstance(scope, ScopeRef)
            or scope != self._scope
            or scope.subject_id != self._principal_id
            or scope.assurance is not Assurance.AUTHENTICATED
        ):
            raise _reader_violation(
                "PRODUCTION_TASK_AUTHORITY_SCOPE_MISMATCH",
                "production Task authority requires the exact authenticated scope",
                ErrorCode.PERMISSION_DENIED,
            )

    def _read_complete_page(
        self,
    ) -> tuple[
        tuple[
            tuple[
                PersistentTaskRecord,
                PersistentAttemptRecord,
                PersistentAdmissionRecord | None,
            ],
            ...,
        ],
        str | None,
        bool,
    ]:
        page = self._store.list_task_read_snapshots_page(
            self._scope,
            limit=self._capacity,
        )
        if page[1] is not None or page[2]:
            raise _reader_violation(
                "PRODUCTION_TASK_AUTHORITY_CAPACITY_EXCEEDED",
                "the complete visible Task set exceeds its closed authority bound",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        return page

    def _read_head(self, task: PersistentTaskRecord):
        events, frozen_head, next_after_seq, has_more = self._store.events_page(
            task.task_id,
            self._scope,
            after_seq=task.event_head - 1,
            limit=1,
        )
        if (
            frozen_head != task.event_head
            or next_after_seq is not None
            or has_more
            or len(events) != 1
            or events[0].seq != task.event_head
        ):
            raise _reader_violation(
                "PRODUCTION_TASK_AUTHORITY_CHANGED",
                "Task event authority changed during its bounded read",
                ErrorCode.STALE,
            )
        event = events[0]
        if (
            event.task_id != task.task_id
            or event.attempt_id != task.attempt_id
            or event.scope != self._scope
            or event.state != task.state.value
            or event.outcome != (None if task.outcome is None else task.outcome.value)
        ):
            raise _reader_violation(
                "PRODUCTION_TASK_EVENT_AUTHORITY_CORRUPT",
                "Task event head does not bind the current canonical Task",
            )
        if (
            task.state is FormalTaskState.TERMINAL
            and event.event_type != "task.terminal"
        ):
            raise _reader_violation(
                "PRODUCTION_TASK_EVENT_AUTHORITY_CORRUPT",
                "terminal Task authority requires the canonical terminal event head",
            )
        if (
            task.state is FormalTaskState.DECISION_REQUIRED
            and event.event_type != "task.decision_required"
            and not (
                task.cancel_requested and event.event_type == "task.cancel_requested"
            )
        ):
            raise _reader_violation(
                "PRODUCTION_TASK_EVENT_AUTHORITY_CORRUPT",
                "decision-required authority requires its canonical event head",
            )
        return event

    @staticmethod
    def _profile(
        task: PersistentTaskRecord,
        attempt: PersistentAttemptRecord,
    ) -> tuple[str, frozenset[tuple[str, str]]]:
        selection = attempt.selection
        if selection is None:
            return _NO_EXECUTOR_PROFILE_DIGEST, frozenset()
        try:
            profile = ExecutorCapabilityProfile.from_dict(
                json.loads(selection.capability_profile_json)
            )
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise _reader_violation(
                "PRODUCTION_TASK_CAPABILITY_AUTHORITY_CORRUPT",
                "persisted Executor capability profile is not canonical",
            ) from error
        if (
            profile.canonical_bytes() != selection.capability_profile_json
            or profile.digest_sha256() != selection.capability_profile_digest
            or profile.adapter_id != selection.adapter_id
            or profile.executor_id != attempt.executor_id
            or profile.executor_id != task.spec.executor_id
        ):
            raise _reader_violation(
                "PRODUCTION_TASK_CAPABILITY_AUTHORITY_CORRUPT",
                "persisted Executor capability binding is inconsistent",
            )
        return profile.digest_sha256(), frozenset(profile.operation_versions)

    @staticmethod
    def _dispatch_control(
        task: PersistentTaskRecord,
        attempt: PersistentAttemptRecord,
        admission: PersistentAdmissionRecord | None,
    ) -> tuple[str, str | None, frozenset[str]]:
        if attempt.selection is None:
            if admission is not None:
                raise _reader_violation(
                    "PRODUCTION_TASK_ADMISSION_AUTHORITY_CORRUPT",
                    "admission facts exist without an Executor selection",
                )
            return "none", None, frozenset()
        if admission is None:
            raise _reader_violation(
                "PRODUCTION_TASK_ADMISSION_AUTHORITY_CORRUPT",
                "selected Task is missing its admission projection",
            )
        fingerprint = hashlib.sha256(
            canonical_json_bytes(admission.to_dict())
        ).hexdigest()
        unclaimed = (
            task.state is FormalTaskState.ACCEPTED
            and not task.cancel_requested
            and not task.dispatch_fenced
            and attempt.state is FormalAttemptState.ACCEPTED
            and attempt.executor_ref is None
            and attempt.source_seq == -1
            and admission.queued
            and not admission.reconciliation_required
            and task.reconciliation_state is None
        )
        queue_operations: set[str] = set()
        if unclaimed:
            if admission.attempt_count == 0 and admission.reason is None:
                queue_operations.add("task.update")
            if (
                admission.attempt_count == 0
                and admission.reason is None
                or admission.attempt_count > 0
                and admission.reason
                in {"EXECUTOR_PROJECT_BUSY", "EXECUTOR_CAPACITY_EXHAUSTED"}
            ):
                queue_operations.add("task.reprioritize")
        return (
            "unclaimed" if unclaimed else "taken_over",
            fingerprint,
            frozenset(queue_operations),
        )

    @staticmethod
    def _operations(
        task: PersistentTaskRecord,
        *,
        operation_versions: frozenset[tuple[str, str]],
        dispatch_control: str,
        queue_operations: frozenset[str],
        has_successor: bool,
        result_digest: str | None,
    ) -> frozenset[str]:
        operations = set(_QUERY_OPERATIONS)
        if (
            task.state is not FormalTaskState.TERMINAL
            and not task.cancel_requested
            and not task.dispatch_fenced
            and ("cancel", "v1") in operation_versions
        ):
            operations.add("task.cancel")
        if (
            task.state is FormalTaskState.RUNNING
            and ("adjust.demo-itinerary-checkpoint", "v1") in operation_versions
        ):
            operations.add("task.adjust")
        if dispatch_control == "unclaimed":
            operations.update(queue_operations)
        if (
            task.state is FormalTaskState.TERMINAL
            and task.outcome is not TerminalOutcome.UNKNOWN
            and not has_successor
            and bool(operation_versions)
            and (
                task.outcome is not TerminalOutcome.COMPLETED
                or result_digest is not None
            )
        ):
            operations.add("task.create_successor")
        return frozenset(operations)

    def list_visible_tasks(self, scope: ScopeRef) -> TaskAuthorityRead:
        self._require_scope(scope)
        first, first_cursor, first_more = self._read_complete_page()
        heads: dict[str, object] = {}
        result_digests: dict[str, str | None] = {}
        operation_versions: dict[str, frozenset[tuple[str, str]]] = {}
        profile_digests: dict[str, str] = {}
        dispatch: dict[str, tuple[str, str | None, frozenset[str]]] = {}
        for task, attempt, admission in first:
            if (
                task.scope != self._scope
                or task.attempt_id != attempt.attempt_id
                or task.task_id != attempt.task_id
            ):
                raise _reader_violation(
                    "PRODUCTION_TASK_LIFECYCLE_AUTHORITY_CORRUPT",
                    "Task and current Attempt authority are inconsistent",
                )
            heads[task.task_id] = self._read_head(task)
            availability, result, _reason = self._store.task_result(
                task.task_id, self._scope
            )
            if availability is TaskResultAvailability.AVAILABLE:
                if result is None:
                    raise _reader_violation(
                        "PRODUCTION_TASK_RESULT_AUTHORITY_CORRUPT",
                        "available Task result has no canonical record",
                    )
                result_digests[task.task_id] = hashlib.sha256(
                    canonical_json_bytes(result.to_dict())
                ).hexdigest()
            else:
                if result is not None:
                    raise _reader_violation(
                        "PRODUCTION_TASK_RESULT_AUTHORITY_CORRUPT",
                        "unavailable Task result exposed a canonical record",
                    )
                result_digests[task.task_id] = None
            profile_digest, versions = self._profile(task, attempt)
            profile_digests[task.task_id] = profile_digest
            operation_versions[task.task_id] = versions
            dispatch[task.task_id] = self._dispatch_control(task, attempt, admission)

        second, second_cursor, second_more = self._read_complete_page()
        if (
            first != second
            or first_cursor != second_cursor
            or first_more != second_more
        ):
            raise _reader_violation(
                "PRODUCTION_TASK_AUTHORITY_CHANGED",
                "visible Task authority changed during its bounded read",
                ErrorCode.STALE,
            )

        for task, _attempt, _admission in second:
            result_digest = result_digests[task.task_id]
            if task.outcome is TerminalOutcome.COMPLETED and result_digest is None:
                raise _reader_violation(
                    "PRODUCTION_TASK_RESULT_AUTHORITY_CORRUPT",
                    "completed Task authority requires its immutable result",
                )
            if (
                task.outcome is not TerminalOutcome.COMPLETED
                and result_digest is not None
            ):
                raise _reader_violation(
                    "PRODUCTION_TASK_RESULT_AUTHORITY_CORRUPT",
                    "non-completed Task authority cannot expose a result digest",
                )

        successors: dict[str, str] = {}
        task_ids = {task.task_id for task, _attempt, _admission in second}
        revisions = {
            task.task_id: task.revision_number for task, _attempt, _admission in second
        }
        for task, _attempt, _admission in second:
            predecessor = task.predecessor_task_id
            if predecessor is None:
                continue
            if (
                predecessor not in task_ids
                or task.revision_number != revisions[predecessor] + 1
            ):
                raise _reader_violation(
                    "PRODUCTION_TASK_LINEAGE_AUTHORITY_INCOMPLETE",
                    "visible Task authority does not contain one exact revision lineage",
                    ErrorCode.CONFLICT,
                )
            if predecessor in successors:
                raise _reader_violation(
                    "PRODUCTION_TASK_LINEAGE_AUTHORITY_CORRUPT",
                    "one predecessor has multiple visible successors",
                )
            successors[predecessor] = task.task_id

        facts: list[AuthenticatedTaskFact] = []
        for task, attempt, _admission in second:
            event = heads[task.task_id]
            control, admission_fingerprint, queue_operations = dispatch[task.task_id]
            result_digest = result_digests[task.task_id]
            successor = successors.get(task.task_id)
            operations = self._operations(
                task,
                operation_versions=operation_versions[task.task_id],
                dispatch_control=control,
                queue_operations=queue_operations,
                has_successor=successor is not None,
                result_digest=result_digest,
            )
            facts.append(
                AuthenticatedTaskFact(
                    task_id=task.task_id,
                    stable_reference=task.task_id,
                    name=task.spec.name,
                    state=TaskState(task.state.value),
                    outcome=task.outcome,
                    revision_number=task.revision_number,
                    event_head=task.event_head,
                    event_head_id=event.event_id,
                    terminal_event_id=(
                        event.event_id
                        if task.state is FormalTaskState.TERMINAL
                        else None
                    ),
                    attempt_id=attempt.attempt_id,
                    attempt_state=AttemptState(attempt.state.value),
                    attempt_outcome=attempt.outcome,
                    capability_profile_digest=profile_digests[task.task_id],
                    supported_operations=operations,
                    result_digest=result_digest,
                    decision_required_event_id=(
                        event.event_id
                        if event.event_type == "task.decision_required"
                        else None
                    ),
                    dispatch_control=control,
                    admission_fingerprint=admission_fingerprint,
                    predecessor_task_id=task.predecessor_task_id,
                    successor_task_id=successor,
                )
            )
        generation = hashlib.sha256(
            canonical_json_bytes(
                {
                    "collection_capability_profile_digest": (
                        self._collection_capability_profile_digest
                    ),
                    "scope": self._scope.to_dict(),
                    "tasks": [
                        fact.canonical_dict()
                        for fact in sorted(facts, key=lambda item: item.task_id)
                    ],
                }
            )
        ).hexdigest()
        return TaskAuthorityRead(
            scope=self._scope,
            generation=generation,
            tasks=tuple(facts),
            collection_capability_profile_digest=(
                self._collection_capability_profile_digest
            ),
        )

    def get_task(self, scope: ScopeRef, task_id: str) -> AuthenticatedTaskFact | None:
        authority = self.list_visible_tasks(scope)
        return next((task for task in authority.tasks if task.task_id == task_id), None)

    def task_status(
        self, scope: ScopeRef, task_id: str
    ) -> AuthenticatedTaskFact | None:
        authority = self.list_visible_tasks(scope)
        return next((task for task in authority.tasks if task.task_id == task_id), None)

    def event_head(self, scope: ScopeRef, task_id: str) -> tuple[int, str]:
        task = self.get_task(scope, task_id)
        if task is None:
            raise _reader_violation(
                "PRODUCTION_TASK_NOT_FOUND",
                "Task authority is unavailable",
                ErrorCode.NOT_FOUND,
            )
        return task.event_head, task.event_head_id

    def result_digest(self, scope: ScopeRef, task_id: str) -> str | None:
        task = self.get_task(scope, task_id)
        if task is None:
            raise _reader_violation(
                "PRODUCTION_TASK_NOT_FOUND",
                "Task authority is unavailable",
                ErrorCode.NOT_FOUND,
            )
        return task.result_digest


class CallLocalProductionOriginAuthority:
    """Verify one classifier-bound source against the canonical commit ledger.

    The expected binding is retained only for the current server call. Natural
    input is also re-proved against ``TurnCommitLedger`` and the exact committed
    text spans. Structured input has no Turn and is accepted only when its full
    semantic binding matches the server-retained call-local value.
    """

    def __init__(
        self,
        *,
        expected_binding: ProductionOriginBinding,
        commit_ledger: TurnCommitLedger | None = None,
    ) -> None:
        if not isinstance(expected_binding, ProductionOriginBinding):
            raise TypeError("PRODUCTION_ORIGIN_BINDING_REQUIRED")
        natural = expected_binding.origin is not ProductionIntentOrigin.STRUCTURED
        if natural != isinstance(commit_ledger, TurnCommitLedger):
            raise ValueError("ORIGIN_COMMIT_AUTHORITY_MISMATCH")
        self._expected = expected_binding
        self._commits = commit_ledger

    def verify_origin(
        self, binding: ProductionOriginBinding
    ) -> TrustedProductionOriginReceipt:
        if (
            not isinstance(binding, ProductionOriginBinding)
            or binding != self._expected
        ):
            raise ValueError("ORIGIN_BINDING_MISMATCH")
        if binding.origin is not ProductionIntentOrigin.STRUCTURED:
            commits = self._commits
            assert commits is not None
            try:
                commit = commits.require_origin(
                    OriginRef(
                        kind="committed_turn",
                        turn_id=binding.source_id,
                        commit_id=binding.commit_id,
                    ),
                    binding.scope,
                )
            except ContractViolation as error:
                raise ValueError("ORIGIN_COMMIT_NOT_ACCEPTED") from error
            if (
                commit.turn_id != binding.source_id
                or hashlib.sha256(commit.canonical_bytes()).hexdigest()
                != binding.commit_sha256
            ):
                raise ValueError("ORIGIN_COMMIT_MISMATCH")
            for extraction in binding.extractions:
                if extraction.source_end > len(commit.text):
                    raise ValueError("ORIGIN_EXTRACTION_MISMATCH")
                content = commit.text[extraction.source_start : extraction.source_end]
                if (
                    hashlib.sha256(content.encode("utf-8")).hexdigest()
                    != extraction.content_sha256
                ):
                    raise ValueError("ORIGIN_EXTRACTION_MISMATCH")
        receipt_id = f"origin.{binding.fingerprint}"
        return TrustedProductionOriginReceipt(
            receipt_id=receipt_id,
            principal_id=binding.principal_id,
            binding_fingerprint=binding.fingerprint,
        )


__all__ = [
    "CallLocalProductionConfirmationClaim",
    "CallLocalProductionConfirmationConsumer",
    "CallLocalProductionOriginAuthority",
    "StoreProductionTaskAuthorityReader",
]
